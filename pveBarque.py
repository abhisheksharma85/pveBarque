from flask import Flask, request
from flask_restful import Resource, Api, reqparse, abort
from json import dumps,loads
from flask_jsonpify import jsonify
from datetime import datetime
from shutil import copyfile
from glob import glob
import subprocess, os, time, json

#defaults
__host = "192.168.100.11"
__port = 6969
path = "/root/barque/"
label = "api"

app = Flask(__name__)
api = Api(app)
todos = {}
vmid = 0

parser = reqparse.RequestParser()
parser.add_argument('file','vmid')

class Backup(Resource):
	def post(self, vmid):
		vmdisk = 'vm-{}-disk-1'.format(vmid)
		timestamp = datetime.strftime(datetime.now(),"_%Y-%m-%d_%H-%M")
		config_file = ""
		config_target = "{}.conf".format(vmid)
		#get config file
		for paths, dirs, files in os.walk('/etc/pve/nodes'):
			if config_target in files:
				config_file = os.path.join(paths, config_target)
				print(config_file)
		#catch if container does not exist
		if len(config_file) == 0:
			return "error, {} is invalid CTID".format(vmid), 400
		#copy config file
		config_dest = "".join([path, vmdisk, timestamp, ".conf"])
		copyfile(config_file, config_dest)
		#create snapshot for backup
		cmd = subprocess.check_output('rbd snap create {}@barque'.format(vmdisk), shell=True)
		#protect snapshot during backup
		cmd = subprocess.check_output('rbd snap protect {}@barque'.format(vmdisk), shell=True)
		#create compressed backup file from backup snapshot
		dest = "".join([path, vmdisk, timestamp, ".lz4"])
		args = ['rbd export --export-format 2 {}@barque - | lz4 -9 - {}'.format(vmdisk, dest)]
		cmd = subprocess.check_output(args, shell=True)#.split('\n') #run command then convert output to list, splitting on newline
		#unprotect barque snapshot
		cmd = subprocess.check_output('rbd snap unprotect {}@barque'.format(vmdisk), shell=True)
		#delete barque snapshot
		cmd = subprocess.check_output('rbd snap rm {}@barque'.format(vmdisk), shell=True)
		return {'Backup file': os.path.basename(dest), 'Config file': os.path.basename(config_dest)}, 201

class Restore(Resource):
	def post(self,vmid):
		fileimg = ""
		fileconf = ""
		filename = os.path.splitext(request.args['file'])[0]
		node = ""
		config_file = ""
		vmdisk = 'vm-{}-disk-1'.format(vmid)
		#check if backup and config files exist
		if 'file' in request.args:
			response = ""
			fileimg = "".join([path, filename, ".lz4"])
			fileconf = "".join([path, filename, ".conf"])
			if not os.path.isfile(fileimg) and not os.path.isfile(fileconf):
				return {'error': "unable to proceed, backup file or config file (or both) does not exist"}, 400
		else:
			return "resource requires a file argument", 400
		#find node hosting container
		config_target = "{}.conf".format(vmid)
		for paths, dirs, files in os.walk('/etc/pve/nodes'):
			if config_target in files:
				config_file = os.path.join(paths, config_target)
				node = config_file.split('/')[4]
				print(node)
		#stop container if not already stopped
		if not loads(subprocess.check_output("pvesh get /nodes/{}/lxc/{}/status/current".format(node,vmid), shell=True))["status"] == "stopped":
			ctstop = subprocess.check_output("pvesh create /nodes/{}/lxc/{}/status/stop".format(node, vmid), shell=True)
		timeout = time.time() + 60
		while True: #wait for container to stop
			stat = loads(subprocess.check_output("pvesh get /nodes/{}/lxc/{}/status/current".format(node,vmid), shell=True))["status"]
			print(stat)
			if stat == "stopped":
				break
			elif time.time() > timeout:
				return "timeout - unable to stop container", 500
		#delete container storage
		imgdel = subprocess.check_output("pvesh delete /nodes/{}/storage/rbd_ct/content/rbd_ct:{}".format(node, vmdisk), shell=True)
		print(imgdel)
		#extract lz4 compressed image file
		filetarget = "".join([path, filename, ".img"])
		uncompress = subprocess.check_output("lz4 -d {} {}".format(fileimg, filetarget), shell=True)
		print(uncompress)
		#import new image
		rbdimp = subprocess.check_output("rbd import --export-format 2 {} {}".format(filetarget, vmdisk), shell=True)
		print(rbdimp)
		#delete uncompressed image file
		rmuncomp = subprocess.check_output("rm {}".format(filetarget), shell=True)
		print(rmuncomp)
		#delete barque snapshot
		cmd = subprocess.check_output('rbd snap rm {}@barque'.format(vmdisk), shell=True)
		#image attenuation for kernel params #Removed after switching to format 2
		# imgatten = subprocess.check_output("rbd feature disable {} object-map fast-diff deep-flatten".format(vmdisk), shell=True)
		# print(imgatten)
		#replace config file
		copyfile(fileconf, config_file)
		#start container
		ctstart = subprocess.check_output("pvesh create /nodes/{}/lxc/{}/status/start".format(node,vmid), shell=True)
		time.sleep(5)
		print(ctstart)
class ListAllBackups(Resource):
	def get(self):
		result = []
		confs = []
		for paths, dirs, files in os.walk(path):
			for f in files:
				if f.endswith('.lz4'):
					result.append(f)
				elif f.endswith('.conf'):
					confs.append(f)
		return {'all backups': result, 'config files': confs}

class ListBackups(Resource):
	def get(self, vmid):
		files = sorted(os.path.basename(f) for f in glob("".join([path, "vm-{}*.lz4".format(vmid)])))
		return {'backups': files}
class DeleteBackup(Resource):
	def post(self,vmid):
		if 'file' in request.args:
			print(request.args['file'])
			fileimg = "".join([path, request.args['file']])
			fileconf = "".join([os.path.splitext(fileimg)[0],".conf"])
			if os.path.isfile(fileimg):
				os.remove(fileimg)
				if os.path.isfile(fileconf):
					os.remove(fileconf)
				return {'file removed': os.path.basename(fileimg)}
			else:
				return {'file does not exist': os.path.basename(fileimg)}
		else:
			return "resource requires a file argument", 400
		

api.add_resource(ListAllBackups, '/barque/')
api.add_resource(ListBackups, '/barque/<int:vmid>')
api.add_resource(Backup, '/barque/<int:vmid>/backup')
api.add_resource(Restore, '/barque/<int:vmid>/restore')
api.add_resource(DeleteBackup, '/barque/<int:vmid>/delete')

if __name__ == '__main__':
        app.run(host=__host,port=__port, debug=True)