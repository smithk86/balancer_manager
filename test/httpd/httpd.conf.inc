# -------
# balancer configs for httpd.conf
# -------

<Proxy balancer://cluster0>
    BalancerMember http://route0/ route=route0
    BalancerMember http://route1/ route=route1
</Proxy>

<Proxy balancer://cluster1>
    BalancerMember http://route0/ route=route0
    BalancerMember http://route1/ route=route1
</Proxy>

<Proxy balancer://cluster2>
    BalancerMember http://route0/ route=route0
    BalancerMember http://route1/ route=route1
    BalancerMember http://route2/ route=route2 status=+D
    BalancerMember http://route3/ route=route3 status=+D
</Proxy>

<Proxy balancer://cluster3>
    BalancerMember http://route0/ route=route0
    BalancerMember http://route1/ route=route1
    BalancerMember http://route2/ route=route2
    BalancerMember http://route3/ route=route3
    BalancerMember http://route4/ route=route4
    BalancerMember http://route5/ route=route5
    BalancerMember http://route6/ route=route6
    BalancerMember http://route7/ route=route7
    BalancerMember http://route8/ route=route8
    BalancerMember http://route9/ route=route9
</Proxy>

<Location /balancer-manager>
    SetHandler balancer-manager
    AuthType Basic
    AuthName "Balancer Manager"
    AuthUserFile conf/htpasswd
    Require valid-user
</Location>
