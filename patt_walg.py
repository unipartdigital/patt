#!/usr/bin/env python3

import patt
import logging
import os
import tempfile
from pathlib import Path
import shutil
from string import Template
import time

logger = logging.getLogger('patt_walg')

def log_results(result, hide_stdout=False):
    error_count=0
    for r in result:
        logger.debug ("hostname: {}".format(r.hostname))
        if not hide_stdout:
            logger.debug ("stdout: {}".format (r.out))
        if r.error is None:
            pass
        elif r.error.strip().startswith("Error: Nothing to do"):
            pass
        else:
            error_count += 1
            logger.error ("stderr: {}".format (r.error))
    return error_count

"""
install postgres packages and dep on each nodes
"""
def walg_init(walg_version, nodes):
    logger.info ("processing {}".format ([n.hostname for n in nodes]))
    patt.host_id(nodes)
    patt.check_dup_id (nodes)

    result = patt.exec_script (nodes=nodes, src="./dscripts/d27.walg.sh",
                               args=['walg_version'], sudo=False)
    ok = all(x == walg_version for x in [n.out for n in result])
    if ok: return True

    payload=None
    if os.path.isfile("./pkg/wal-g.linux-amd64.tar.gz"):
        payload="./pkg/wal-g.linux-amd64.tar.gz"

    result = patt.exec_script (nodes=nodes, src="./dscripts/d27.walg.sh", payload=payload,
                                args=['init'] + [walg_version], sudo=False)
    log_results (result)
    return all(x == True for x in [bool(n.out) for n in result])

"""
install util packages to allow sftp access
"""
def walg_ssh_archiving_init(nodes):
    logger.info ("processing {}".format ([n.hostname for n in nodes]))
    patt.host_id(nodes)
    # patt.check_dup_id (nodes)

    result = patt.exec_script (nodes=nodes, src="./dscripts/d27.walg.sh",
                                args=['ssh_archiving_init'], sudo=True)
    log_results (result)
    #return all(x == True for x in [bool(n.out) for n in result])

"""
gen a walg ssh key on each peer and return all the public key (on success)
"""
def walg_ssh_gen(cluster_name, nodes, postgres_user='postgres'):
    logger.info ("processing {}".format ([n.hostname for n in nodes]))
    patt.host_id(nodes)
    patt.check_dup_id (nodes)

    result = patt.exec_script (nodes=nodes, src="./dscripts/d27.walg.sh",
                               args=['ssh_archive_keygen'] + [cluster_name] + [postgres_user],
                               sudo=True, log_call=True)
    log_results (result, hide_stdout=True)
    assert all(x == True for x in [bool(n.out) for n in result])
    return [n.out for n in result]

"""
gen an initial known_hosts or check if valid
"""
def walg_ssh_known_hosts(cluster_name, nodes, archiving_server, archiving_server_port=22):
    logger.info ("processing {}".format ([n.hostname for n in nodes]))
    patt.host_id(nodes)
    patt.check_dup_id (nodes)

    result = patt.exec_script (nodes=nodes, src="./dscripts/d27.walg.sh",
                               args=['ssh_known_hosts'] + [cluster_name] +
                               [archiving_server] + [archiving_server_port],
                               sudo=True)
    log_results (result)
    return not any(x == True for x in [bool(n.error) for n in result if hasattr(n,'error')])

"""
add the public keys into the archive server
"""
def walg_authorize_keys(cluster_name, nodes, keys=[]):
    patt.host_id(nodes)
    # patt.check_dup_id (nodes)
    with tempfile.NamedTemporaryFile(mode='w+', encoding='ascii') as tmpl_file:
        for k in keys + [""]:
            print("{}".format (k), file=tmpl_file)
        tmpl_file.flush()
        result = patt.exec_script (nodes=nodes, src="./dscripts/d27.walg.sh",
                                   payload=tmpl_file.name,
                                   args=['ssh_authorize_keys'] + [cluster_name] +
                                   [os.path.basename (tmpl_file.name)], sudo=True)
        log_results (result)
    return not any (x == True for x in [bool(n.error) for n in result if hasattr(n,'error')])

"""
preapare the archive server for chroot sftp
"""
def walg_archiving_standalone_sftpd(cluster_name, nodes, listen_addr="::0", listen_port=2222):
    patt.host_id(nodes)
    # patt.check_dup_id (nodes)

    tmpl="./config/sftpd.service"
    result = patt.exec_script (nodes=nodes, src="./dscripts/tmpl2file.py",
                               payload=tmpl,
                               args=['-t'] + [os.path.basename (tmpl)] +
                               ['-o'] + ["/etc/systemd/system/{}".format (os.path.basename (tmpl))] +
                               ['--chmod'] + ['644'],
                               sudo=True)
    log_results (result)
    assert not any(x == True for x in [bool(n.error) for n in result if hasattr(n,'error')])

    tmpl="./config/sftpd_config"
    result = patt.exec_script (nodes=nodes, src="./dscripts/tmpl2file.py",
                               payload=tmpl,
                               args=['-t'] + [os.path.basename (tmpl)] +
                               ['-o'] + ["/etc/ssh/{}".format (os.path.basename (tmpl))] +
                               ['--dictionary_key_val'] +
                               ["listen_address=[{}]:{}".format(listen_addr, listen_port)] +
                               ['--dictionary-rhel'] +
                               ["subsystem=/usr/libexec/openssh/sftp-server"] +
                               ['--dictionary-fedora'] +
                               ["subsystem=/usr/libexec/openssh/sftp-server"] +
                               ['--dictionary-centos'] +
                               ["subsystem=/usr/libexec/openssh/sftp-server"] +
                               ['--dictionary-debian'] +
                               ["subsystem=/usr/lib/openssh/sftp-server"] +
                               ['--dictionary-ubuntu'] +
                               ["subsystem=/usr/lib/openssh/sftp-server"] +
                               ['--chmod'] + ['644'],
                               sudo=True)
    log_results (result)
    assert not any(x == True for x in [bool(n.error) for n in result if hasattr(n,'error')])

"""
preapare the archive server for chroot sftp
"""
def walg_archiving_add(cluster_name, nodes, port):
    patt.host_id(nodes)
    patt.check_dup_id (nodes)
    if not port == 22:
        assert port > 1024, "error: restricted to unreserved or default ssh port only"
        walg_archiving_standalone_sftpd(cluster_name=cluster_name, nodes=nodes,
                                        listen_addr="::0", listen_port=port)

    result = patt.exec_script (nodes=nodes, src="./dscripts/d27.walg.sh",
                               args=['ssh_archiving_add'] + [cluster_name] + [port], sudo=True)
    log_results (result)
    return all(x == True for x in [bool(n.out == "drwx--x--x {}.{} {}".format (
        cluster_name, "walg", "/var/lib/walg/" + cluster_name)) for n in result])

"""
s3 json config
"""
def walg_s3_json(postgres_version, cluster_name, nodes, walg_store):
    logger.info ("processing {}".format ([n.hostname for n in nodes]))
    patt.host_id(nodes)
    patt.check_dup_id (nodes)
    comd="./dscripts/tmpl2file.py"
    tmpl="./config/walg-s3.json"
    count=0
    isok = []
    logger.debug ("walg_s3_json: {}".format(walg_store))
    for c in walg_store:
        logger.debug ("walg_s3_json: {}".format(c))
        if 'method' in c and c['method'] == 's3':
            endpoint=c['endpoint']
            assert endpoint, "missing endpoint definition"
            prefix=c['prefix']
            assert prefix, "missing prefix definition"
            if not (prefix.endswith(cluster_name) or prefix.endswith(cluster_name + '/')):
                prefix=prefix + '/' + cluster_name
            region=c['region']
            assert region, "missing region definition"
            if 'force_path_style' in c:
                force_path_style=c['force_path_style']
            else:
                force_path_style='true'
            if 'profile' in c:
                profile=c['profile']
            else:
                profile=''

            if count == 0:
                s3_config_file=".walg.json"
            else:
                s3_config_file="walg-{}-s3.json".format(count)

            result = patt.exec_script (nodes=nodes, src="./dscripts/d27.walg.sh", payload=[comd, tmpl],
                                       args=['s3_json'] + [postgres_version] + [cluster_name] +
                                       [endpoint] + [prefix] + [region] + [profile] +
                                       [force_path_style] + [s3_config_file] +
                                       ['postgres'] + [os.path.basename (comd)] + [os.path.basename (tmpl)],
                                       sudo=True)
            isok.append(not any(x == True for x in [bool(n.error) for n in result if hasattr(n, 'error')]))
            log_results (result)
        count += 1
    return all(x == True for x in isok)

"""
sh json config
"""
def walg_sh_json(postgres_version, cluster_name, nodes, walg_store):
    logger.info ("processing {}".format ([n.hostname for n in nodes]))
    patt.host_id(nodes)
    patt.check_dup_id (nodes)
    comd="./dscripts/tmpl2file.py"
    tmpl="./config/walg-sh.json"
    count=0
    isok = []
    logger.debug ("walg_sh_json: {}".format(walg_store))
    for c in walg_store:
        logger.debug ("walg_sh_json: {}".format(c))
        if 'method' in c and c['method'] == 'sh':
            host=c['host']
            assert host, "missing ssh host definition"
            if 'prefix' in c:
                prefix=c['prefix']
            if not prefix:
                prefix=cluster_name
            if not (prefix.endswith(cluster_name) or prefix.endswith(cluster_name + '/')):
                prefix=prefix + '/' + cluster_name
            (login, hostname, port) = patt.ipv6_nri_split (host)
            if not login:
                login = cluster_name
            if not port:
                port = 22
            identity_file=None
            if 'identity_file' in c:
                identity_file=c['identity_file']
            if not identity_file:
                identity_file="walg_rsa"

            if count == 0:
                sh_config_file=".walg.json"
            else:
                sh_config_file="walg-{}-sh.json".format(count)

            result = patt.exec_script (nodes=nodes, src="./dscripts/d27.walg.sh", payload=[comd, tmpl],
                                       args=['sh_json'] + [postgres_version] + [cluster_name] +
                                       [hostname] + [port] + [prefix] + [login] +
                                       [identity_file] + [sh_config_file] +
                                       ['postgres'] + [os.path.basename (comd)] + [os.path.basename (tmpl)],
                                       sudo=True)
            isok.append(not any(x == True for x in [bool(n.error) for n in result if hasattr(n, 'error')]))
            log_results (result)
        count += 1
    return all(x == True for x in isok)

"""
return a list of tuple of node [(sftpd_peers, sftpd_service)]
"""
def sftpd_peers_service(walg_store, sftpd_peers):
    result=[]
    sh_store = (patt.to_nodes(
        [c['host'] for c in walg_store if c['method'] == 'sh' and 'host' in c],
        None, None))
    for p in sftpd_peers:
        for s in sh_store:
            if p.hostname == s.hostname:
                result.append((p, s))
    return result
