#!/bin/bash

srcdir=$(cd $(dirname $0); pwd)
# Exit the script on errors:
set -e
trap '{echo "$0 FAILED on line $LINENO!; rm -f $0 ;}" | tee ${srcdir}/$(basename $0).log' ERR
# clean up on exit
trap "{ rm -f $0; }" EXIT

# Catch unitialized variables:
set -u

#
ETCD_CONF="/etc/etcd/etcd.conf"
#

# return self from list of ip:node_name
# ipv6 only
get_self_node () {
    cluster_nodes=$*
    for i in $(ip -6 addr show scope global | grep inet6 | awk '{print $2}' | cut -d '/' -f 1); do
        for j in ${cluster_nodes}; do
            if echo ${j} | grep -q ${i}; then
                echo ${j}
                return 0
            fi
        done
    done
    echo ""
    return 1
}

get_member_id () {
    name=$1
    etcdctl member list | grep "name=$name[[:space:]]\+" | cut -d : -f 1
}

# param
# 1: cluster_name: <string>
# 2,n cluster_nodes: <machineID | HostID>_<Hostname | IPV4 | [IPV6]>
init() {
    cluster_name="$1"
    shift 1
    cluster_nodes=$*

    SELF_ID=$(hostid || cat /etc/machine-id 2> /dev/null)

    if systemctl status etcd; then
        # # etcd is running
        self_found=""
        peers=$(etcdctl member list | sed  -e 's|.*name=\([[:alnum:]]\+\) .*|\1|')
        for peer in ${peers}; do
            if [ "${SELF_ID}" == "${peer}" ] ; then
                self_found="true"
            fi
        done
        if [ "${self_found}" != "true" ]; then
            echo "${SELF_ID} etcd running but member not in peers" 1>&2 ; exit 1
        fi
        # we have nothing to do with this cluster

        query_id="$(etcdctl get /etcd/${cluster_name}/${SELF_ID})"
        leader=$(etcdctl member list | sed -e '/\(.*isleader=[^true].*\)/Id' \
                                           -e 's|.*name=\([[:alnum:]]\+\) .*|\1|')
        if [ "${leader}" == "${SELF_ID}" -a "${query_id}" == "${SELF_ID}" ]; then
            # run any command that need to be done only on one node (leader node)

            # check if any unreachable peers need to be removed
            {
                for id in $(basename -a $(etcdctl ls /etcd/${cluster_name}/)); do
                    if ! $(echo "${cluster_nodes}" | grep -q "${id}_"); then
                        # id not in the list of cli nodes
                        # check if unreachable
                        member_id=$(get_member_id "${id}")
                        if $(etcdctl cluster-health | grep "[[:space:]]${member_id}[[:space:]]" | grep -q "unreachable:"); then
                            etcdctl member remove "${member_id}"
                            etcdctl rm "/etcd/${cluster_name}/${id}"
                            # for p in $(etcdctl member list | sed -e "s|.*peerURLs=\([^[:space:]]*\).*|\1|"); do
                            #     etcdctl member update ${p}
                            # done
                        fi
                    fi
                done
            }

        elif [ "${query_id}" == "${SELF_ID}" ]; then
            # we are already configured as member
            echo "${SELF_ID} already member of ${cluster_name}"
            exit 0
        fi

        exit 1
    fi

    sudo yum install -y etcd

    self_node=$(get_self_node "${cluster_nodes}")
    self_id=$(echo "$self_node" | cut -d '_' -f 1)
    self_ip=$(echo "$self_node" | cut -d '_' -f 2)
    if [ "x${self_id}" != "x${SELF_ID}" ]; then
        exit 1
    else
        ping6 -c 1 "${self_ip}"
    fi

    ETCD_DATA_DIR=/var/lib/etcd/${self_id}
    mkdir -p -m 700 "${ETCD_DATA_DIR}"
    chown etcd.etcd "${ETCD_DATA_DIR}"

    etcd_initial_cluster=""
    for n in ${cluster_nodes}; do
        ID=$(echo ${n} | cut -d '_' -f 1)
        IP=$(echo ${n} | cut -d '_' -f 2)
        etcd_initial_cluster="${etcd_initial_cluster},${ID}=https://[${IP}]:2380"
    done
    etcd_initial_cluster=$(echo ${etcd_initial_cluster} | sed -e 's|^,||')

    if [ ! -f "/etc/etcd/etcd.conf.ori" -a -f "/etc/etcd/etcd.conf" ]; then
        cp -a "/etc/etcd/etcd.conf" "/etc/etcd/etcd.conf.ori"
    fi

    cat <<EOF > /etc/etcd/etcd.conf
#[Member]
ETCD_DATA_DIR="${ETCD_DATA_DIR}"
ETCD_LISTEN_PEER_URLS="https://[::]:2380"
ETCD_LISTEN_CLIENT_URLS="http://[::]:2379"
ETCD_NAME="${self_id}"
#[Clustering]
ETCD_INITIAL_ADVERTISE_PEER_URLS="https://[${self_ip}]:2380"
ETCD_ADVERTISE_CLIENT_URLS="http://[${self_ip}]:2379"
ETCD_INITIAL_CLUSTER="${etcd_initial_cluster}"
ETCD_INITIAL_CLUSTER_TOKEN="${cluster_name}"
#[Security]
#ETCD_CERT_FILE=""
#ETCD_KEY_FILE=""
#ETCD_CLIENT_CERT_AUTH="false"
#ETCD_TRUSTED_CA_FILE=""
#ETCD_AUTO_TLS="false"
#ETCD_PEER_CERT_FILE=""
#ETCD_PEER_KEY_FILE=""
#ETCD_PEER_CLIENT_CERT_AUTH="false"
#ETCD_PEER_TRUSTED_CA_FILE=""
ETCD_PEER_AUTO_TLS="true"
#
#[Logging]
#ETCD_DEBUG="false"
#ETCD_LOG_PACKAGE_LEVELS=""
#ETCD_LOG_OUTPUT="default"
EOF

    systemctl start etcd
    for i in 1 2 3 4 5 6 7 8 9 10; do
        etcdctl cluster-health
        if [ "$?" -eq 0 ]; then break; fi
        if [ "$i" -gt 9 ]; then exit 1; fi
        sleep 3
    done

    etcdctl set "/etcd/${cluster_name}/${self_id}" "${self_id}"
    systemctl enable etcd
}

check () {
    :
}

case "$1" in
    'init')
        shift 1; init "$@"
        ;;
    'check')
        shift 1; check "$@"
        ;;
    *)
        echo "usage $0 [init cluster_name cluster_nodes (id_ipv6)]"
        ;;
esac
