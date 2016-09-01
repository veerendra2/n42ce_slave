# About this Repo

This is the Git repo of the Docker [official image](https://docs.docker.com/docker-hub/official_repos/) for [n42ce_slave](https://hub.docker.com/r/n42inc/n42ce_slave/). See [the Docker Hub page](https://hub.docker.com/r/n42inc/n42ce_master/) for the full readme on how to use this Docker image and for information regarding contributing and issues.

[n42ce_slave](https://hub.docker.com/r/n42inc/n42ce_slave/) resides in swarm slave node's and listen events from redis.[n42ce_master](https://hub.docker.com/r/n42inc/n42ce_master/) resides in swarm master , listen swarm events and send to redis.


## How to use this image
1.Drop a mail to <b>info@networks42.com</b> for the key
2.Launch docker image with provided key

### Without a Dockerfile
If you don't want to include a Dockerfile in your project, it is sufficient to do the following:
```
docker run --net=host --privileged --volume=/var/lib/docker/:/var/lib/docker:ro    --volume=/:/n42/  --volume=/sys/fs/cgroup/:/sys/fs/cgroup/:ro -e key=test_key  -it --name=n42ce_slave -d  veerendrav2/n42ce_slave:latest
```
3.Ports open on firewall :
```
   redis: Port:6379  IP: 52.8.104.253   
   tsdb : Port:4343  IP: 52.8.104.253
```
4.Log into [http://52.8.104.253:8080/](http://54.67.112.100:8080/)  with provided crediantials.
