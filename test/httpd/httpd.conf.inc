# -------
# add required modules
# -------

LoadModule ssl_module modules/mod_ssl.so
LoadModule proxy_module modules/mod_proxy.so
LoadModule proxy_http_module modules/mod_proxy_http.so
LoadModule proxy_balancer_module modules/mod_proxy_balancer.so
LoadModule slotmem_shm_module modules/mod_slotmem_shm.so
LoadModule lbmethod_byrequests_module modules/mod_lbmethod_byrequests.so

# -------
# balancer configs for httpd.conf
# -------

<Proxy balancer://cluster0>
    BalancerMember http://route00/ route=route00
    BalancerMember http://route01/ route=route01
</Proxy>

<Proxy balancer://cluster1>
    BalancerMember http://route10/ route=route10
    BalancerMember http://route11/ route=route11
</Proxy>

<Proxy balancer://cluster2>
    BalancerMember http://route20/ route=route20
    BalancerMember http://route21/ route=route21
    BalancerMember http://route22/ route=route22 status=+H
    BalancerMember http://route23/ route=route23 status=+H
</Proxy>

<Proxy balancer://cluster3>
    BalancerMember http://route30/ route=route30 
    BalancerMember http://route31/ route=route31
    BalancerMember http://route32/ route=route32 status=+HD
    BalancerMember http://route33/ route=route33 status=+HD
    BalancerMember http://route34/ route=route34 status=+HD
    BalancerMember http://route35/ route=route35 status=+HD
    BalancerMember http://route36/ route=route36 status=+HD
    BalancerMember http://route37/ route=route37 status=+HD
    BalancerMember http://route38/ route=route38 status=+HD
    BalancerMember http://route39/ route=route39 status=+HD
</Proxy>

<Proxy balancer://cluster4>
    BalancerMember http://route45/ route=route45 lbset=1
    BalancerMember http://route46/ route=route46 lbset=1 status=+H
    BalancerMember http://route47/ route=route47 lbset=1 status=+H
    BalancerMember http://route48/ route=route48 lbset=1 status=+H
    BalancerMember http://route49/ route=route49 lbset=1 status=+H
    BalancerMember http://route40/ route=route40 lbset=0
    BalancerMember http://route41/ route=route41 lbset=0 status=+H
    BalancerMember http://route42/ route=route42 lbset=0 status=+H
    BalancerMember http://route43/ route=route43 lbset=0 status=+H
    BalancerMember http://route44/ route=route44 lbset=0 status=+H
</Proxy>

<Location /balancer-manager>
    SetHandler balancer-manager
    AuthType Basic
    AuthName "Balancer Manager"
    AuthUserFile conf/htpasswd
    Require valid-user
</Location>

ExtendedStatus on
<Location /server-status>
    SetHandler server-status
    AuthType Basic
    AuthName "Server Status"
    AuthUserFile conf/htpasswd
    Require valid-user
</Location>
