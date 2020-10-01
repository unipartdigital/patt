#!/usr/bin/env python3

import argparse
import pwd
import subprocess
import sys
import os
from string import Template
from fcntl import flock,LOCK_EX, LOCK_NB, LOCK_UN

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-c','--cluster_name', help='postgres system user', default="postgres")
    parser.add_argument('-u','--postgres_user', help='postgres system user', default="postgres")
    parser.add_argument('-s','--ssl_script', help='cert_generator script', required=True)
    # peers arguments should look like: -p p1 p2 p3 -e e1 e2 e3 -x x1 x2 x3 -c c1 c2 c3
    parser.add_argument('-p','--peers', help='postgres peers', required=True, nargs='+')

    parser.add_argument('--ca_path', help='path to ca certificat', default=None, required=False)
    parser.add_argument('--ca_key_path', help='path to private key', default=None, required=False)
    parser.add_argument('--cert_country_name', help='Country Name', default="UK")
    parser.add_argument('--cert_state_or_province_name', help='State or Province Name', default="United Kingdom")
    parser.add_argument('--cert_locality_name', help='Locality Name', default="Cambridge")
    parser.add_argument('--cert_organization_name', help='Organization Name', default="Patroni Postgres Cluster")
    parser.add_argument('--cert_common_name', help='Common Name')
    parser.add_argument('--cert_dns', help='list of dns names', action='append', required=False, default=[])
    parser.add_argument('--cert_ip', help='list of IPs', action='append', required=False, default=[])
    parser.add_argument('--cert_not_valid_after', help='not valid after n days', type=int, default=365)
    parser.add_argument('--cert_path', help='path to certificat', default=None, required=False)
    parser.add_argument('--cert_key_pass_phrase', help='private key passphrase', default=None, required=False)
    parser.add_argument('--cert_key_size', help='private key size', type=int, default=4096, required=False)
    parser.add_argument('--cert_key_path', help='path to private key', default=None, required=False)

    parser.add_argument('--lock_dir', help='lock directory', required=False, default="/tmp")

    args = parser.parse_args()
    os.chdir (os.path.dirname (__file__))

    ###
    lock_filename = args.lock_dir + '/' + os.path.basename (__file__).split('.')[0] + '.lock'
    if not os.path.exists(lock_filename):
        lockf = open(lock_filename, "w+")
        lockf.close()
    lockf = open(lock_filename, "r")
    lock_fd = lockf.fileno()
    flock(lock_fd, LOCK_EX | LOCK_NB)
    ###

    pgh=pwd.getpwnam(args.postgres_user).pw_dir
    cmd=None
    ip_arg=[]
    dns_arg=[]
    if args.peers:
        ip_arg=['--cert_ip'] + args.peers
    if args.cert_dns:
        dns_arg=['--cert_dns'] + args.cert_dns
    cmd_list=[
        "/usr/bin/python3",
        args.ssl_script,
        "cli",
        "--ca_path", pgh + '/.postgresql/root.crt',
        "--ca_key_path", pgh + '/.postgresql/root.key',
        "--cert_country_name", args.cert_country_name,
        "--cert_state_or_province_name", args.cert_state_or_province_name,
        "--cert_locality_name", args.cert_locality_name,
        "--cert_organization_name", args.cert_organization_name,
        "--cert_common_name", args.cluster_name,
        "--cert_not_valid_after", str(args.cert_not_valid_after),
        "--cert_path", pgh + '/server.crt',
        "--cert_key_size", str(args.cert_key_size),
        "--cert_key_path", pgh + '/server.key'] +  ip_arg + dns_arg

    if args.cert_key_pass_phrase is not None:
            cmd_list.append("--cert_key_pass_phrase")
            cmd_list.append(args.cert_key_pass_phrase.encode('utf8'))
    try:
        cmd = subprocess.run (cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf8',
                              check=False)
        if cmd.returncode == 0:
            pass
        else:
            raise Exception(cmd.stderr)
    except:
        raise

    pg_home=pwd.getpwnam(args.postgres_user).pw_dir
    uid=pwd.getpwnam(args.postgres_user).pw_uid
    gid=pwd.getpwnam(args.postgres_user).pw_gid
    for f in [pgh + '/server.crt', pgh + '/server.key']:
        os.chown(f, uid, gid)
        os.chmod(f, 0o600)

    ###
    flock(lock_fd, LOCK_UN)
    lockf.close()
    try:
        os.remove(lock_filename)
    except OSError:
        pass
    ###
