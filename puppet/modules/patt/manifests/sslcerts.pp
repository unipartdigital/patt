class patt::sslcerts(
 $ssl_cert_dir = "/etc/puppetlabs/code/environments/production/modules/patt/ssl-cert",
 $postgres_home = "/var/lib/pgsql",
)
{

 $ca_crt=generate("$ssl_cert_dir/00-generator.sh", "$patt::cluster_name", "root_cert")
 $ca_key=generate("$ssl_cert_dir/00-generator.sh", "$patt::cluster_name", "root_key")

 file{"${postgres_home}/.postgresql/":
    ensure  =>  directory,
    owner   => postgres,
    group   => postgres,
    mode    => '0700',
    require => [Package["postgresql${patt::postgres_release}-server"]],
 }

 file {"${postgres_home}/.postgresql/root.crt":
    content => $ca_crt,
    owner   => root,
    group   => root,
    mode    => '0644',
    require => [Package["postgresql${patt::postgres_release}-server"], File["${postgres_home}/.postgresql/"]],
 }

 file {"${postgres_home}/.postgresql/root.key":
    content => $ca_key,
    owner   => postgres,
    group   => postgres,
    mode    => '0600',
    require => [Package["postgresql${patt::postgres_release}-server"], File["${postgres_home}/.postgresql/"]],
 }

}