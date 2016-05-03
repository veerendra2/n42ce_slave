import interface_metrics
import cpu
import docker_stats
import time,os
import yaml,sys

try:
     	f = open('/opt/n42Agents/stats/config.yml', 'r')
     	config = yaml.load(f)
        interval = config['tsdb']['interval']#os.environ['interval']
	hostname = os.uname()[1]
	config['node_config_files']['host'] = hostname
    	while True:
		#interface_metrics.main(config)
		cpu.main(config)
		docker_stats.main(config)
		time.sleep(interval)
except Exception ,e :
        print "Exception:",e,"At Line Number {}".format(sys.exc_info()[-1].tb_lineno)
