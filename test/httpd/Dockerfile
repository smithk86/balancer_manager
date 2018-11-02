ARG FROM
FROM ${FROM}
COPY htpasswd conf/
COPY httpd.conf.inc* /tmp/
RUN cat /tmp/httpd.conf.inc.24 >> conf/httpd.conf && \
    cat /tmp/httpd.conf.inc >> conf/httpd.conf && \
    rm -rf /tmp/*
