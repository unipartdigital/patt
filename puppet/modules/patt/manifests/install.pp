class patt::install (
 $install_dir='/usr/local/libexec/patt'
)
{
 file {
  "$install_dir":
   ensure => 'directory',
   source => 'puppet:///modules/patt/patt',
   recurse => 'remote',
   path => $install_dir,
   owner => 'root',
   group => 'root',
   mode  => '0644',
 }
 file {
  "${install_dir}/patt_cli.py":
   ensure => 'file',
   source => 'puppet:///modules/patt/patt/patt_cli.py',
   recurse => 'false',
   path => "${install_dir}/patt_cli.py",
   owner => 'root',
   group => 'root',
   mode  => '0755',
 }

 exec { 'make_dep':
    command => "/usr/bin/python3 -c 'import paramiko;import sys; paramiko.__version__[:3] >= '2.7' or sys.exit(1)' || /usr/bin/pip3 install -U --user paramiko",
    user => 'patt',
    environment => ['HOME=/home/patt'],

 }

}
