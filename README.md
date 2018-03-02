# pveBarque
Standalone API for backup and restore of ceph vm images

Inspired by [eve4pve-barc](https://github.com/EnterpriseVE/eve4pve-barc) by Daniele Corsini, this API is intended to provide basic orchestration of backups, restorations, and possibly snapshots as well as providing information regarding backup status and lists.
This is being developed for an environment in which one Proxmox VE node is dedicated for storage and connected to the ceph cluster, though it could be used on a node with load. However no optimizations for performance, efficiency, and niceness are being planned explicitly. 
