# -------
# add required modules
# -------

LoadModule watchdog_module modules/mod_watchdog.so
LoadModule proxy_hcheck_module modules/mod_proxy_hcheck.so

# -------
# balancer configs for httpd.conf
# -------

<Proxy balancer://cluster5>
    BalancerMember http://route50/ route=route50 hcmethod=TCP
    BalancerMember http://route51/ route=route51 hcmethod=TCP
</Proxy>
