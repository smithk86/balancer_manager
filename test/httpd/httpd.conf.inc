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

<Location /balancer-manager>
    SetHandler balancer-manager
    AuthType Basic
    AuthName "Balancer Manager"
    AuthUserFile conf/htpasswd
    Require valid-user
</Location>
