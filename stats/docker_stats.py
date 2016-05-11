import os,subprocess,linecache,time,math
import potsdb,sys
import json,yaml
metric1="proc.cpu.util"  # %
metric2="mem.usage"      # MB
metric9="mem.free"      # MB
metric3="mem.total"      # MB
metric4="mem.usage.percent"  # %
metric5="docker.net.tx"       # kB
metric6="docker.net.rx"       # kB
metric7="disk.block.read"   # MB
metric8="disk.block.write"  # MB
metric12="docker.rx.drops"    #
metric13="docker.tx.drops"    #

def get_containers(string):
        directory = "/sys/fs/cgroup/cpuacct"+string
        return next(os.walk(directory))[1]
def read_file(file_name,line_no):
    if line_no is not None:
        return linecache.getline(file_name, line_no)
    else:
        l1=list()
        file=open(file_name,'r')
        lists=file.readlines()
        for a in lists[2:len(lists)-1]:
            l1.append(a)
        return l1

def get_all_values(string,config):
        values_dict = {}
        containers=get_containers(string)
	if os.path.isfile("/var/lib/docker/containers/"+containers[0]+"/config.v2.json"):
		config['node_config_files']['config_json'] = "/config.v2.json"
	else:
		config['node_config_files']['config_json'] = "/config.json"
        for c in containers:
            try:
                cid = c[:12]
                max_memory_f = "/sys/fs/cgroup/memory"+ string + c + "/memory.limit_in_bytes"
                usage_memory_f = "/sys/fs/cgroup/memory"+ string + c + "/memory.usage_in_bytes"
                docker_mem_stat_f  = "/sys/fs/cgroup/memory" +string + c + "/memory.stat"
                docker_cpu_f = "/sys/fs/cgroup/cpuacct"+ string + c +  "/cpuacct.usage"
                sys_cpu_f = config['node_config_files']['cpu_stats']#"/proc/stat"
                docker_io_f = "/sys/fs/cgroup/blkio"+ string + c + "/blkio.throttle.io_service_bytes"
		container_pid_f = "/var/lib/docker/containers/"+ c + config['node_config_files']['config_json']
		
                max_memory = int(read_file(max_memory_f,1))
                usage_memory = int(read_file(usage_memory_f,1))
                docker_pagefults =  read_file(docker_mem_stat_f,10)
                docker_rss =  read_file(docker_mem_stat_f,19)

                docker_cpu = int(read_file(docker_cpu_f,1))
                sys_cpu_l = read_file(sys_cpu_f,1).split()
                sys_cpu = 0
                for i in sys_cpu_l[1:]:
                        sys_cpu = sys_cpu + int(i)

                docker_io_read = float(read_file(docker_io_f,1).split()[2])
                docker_io_write = float(read_file(docker_io_f,2).split()[2])

                container_pid = open(container_pid_f,'r')
                for line in container_pid:
                        j = json.loads(line)
                        docker_net_f = config['node_config_files']['proc']+ str(j['State']['Pid'])+"/net/dev"
                        v = read_file(docker_net_f,None)[0].split()

                values_dict[cid] = {'max_memory':max_memory,'usage_memory':usage_memory,'docker_cpu':docker_cpu,'sys_cpu':sys_cpu,'docker_io_read':docker_io_read,'docker_io_write':docker_io_write,'docker_pagefults':docker_pagefults,'docker_rss':docker_rss,'intface_stat':v}
            except Exception as e:
                print "Exception!",e
                continue
        linecache.clearcache()
        return values_dict


def main(config):
     tsdbIp = config['tsdb']['tsdbIp']
     tsdbPort = config['tsdb']['tsdbPort']
     hostname = config['node_config_files']['host']
     host_mem_size = round((float(read_file(config['node_config_files']['memory'],1).split(":")[1].split()[0]))/(2**10),3)
     string = config['docker_container_config_files']['string']
     try:
	sleeptime = 3
        a = get_all_values(string,config)
        time.sleep(sleeptime)
        b = get_all_values(string,config)
        #print a,b
        #cidname_dict = cidname_map()
        metrics = potsdb.Client(tsdbIp, port=tsdbPort,qsize=1000, host_tag=True, mps=100, check_host=True)
        for k, i in a.iteritems():
          #memory
                max_mem = b[k]['max_memory']/pow(2,20)
                if max_mem >  22368547 :
                        max_mem = host_mem_size
                mem_usage = b[k]['usage_memory']/pow(2,20)
                docker_mem_percent = (mem_usage * 100)/max_mem
		mem_free = max_mem - mem_usage
          #cpu
                docker_cpu = ((b[k]['docker_cpu'] - a[k]['docker_cpu'])/sleeptime)*(pow(10,-9))
                sys_cpu = ((b[k]['sys_cpu'] - a[k]['sys_cpu'])/sleeptime)*(pow(10,-2))
                docker_cpu_percent=(docker_cpu/sys_cpu)*100
          #disk
                docker_io_read = round(((b[k]['docker_io_read'] - a[k]['docker_io_read'])/sleeptime)/pow(2,20),3)
                docker_io_write = round(((b[k]['docker_io_write'] - a[k]['docker_io_write'])/sleeptime)/pow(2,20),3)
          #interface
                intface_stat1 = a[k]['intface_stat']
                intface_stat2 = b[k]['intface_stat']
                rx = round(((float(intface_stat2[1])- float(intface_stat1[1]))/sleeptime)/pow(2,10),4)# - float(intface_stat1[1])
                tx = round(((float(intface_stat2[9]) - float(intface_stat1[9]))/sleeptime)/pow(2,10),4)# - float(intface_stat1[9])
                rx_drop =  round(((float(intface_stat2[4]) - float(intface_stat1[4]))/sleeptime))# - float(intface_stat1[4])
                tx_drop =  round(((float(intface_stat2[12]) - float(intface_stat1[12]))/sleeptime))
                interface = intface_stat2[0].split(":")[0]
                #print k,docker_cpu_percent,docker_mem_percent,docker_io_read,docker_io_write,rx,tx,rx_drop,tx_drop

                metrics.send(metric6,rx,interface=interface,host=k,nodename=hostname)
                metrics.send(metric5,tx,interface=interface,host=k,nodename=hostname)
                metrics.send(metric12,rx_drop,interface=interface,host=k,nodename=hostname)
                metrics.send(metric13,tx_drop,interface=interface,host=k,nodename=hostname)
                print metric6,rx,"interface="+interface,"host="+k,"nodename=",hostname
                print metric5,tx,"interface="+interface+"host="+k,"nodename="+hostname
                print metric12,rx_drop,"interface="+interface,"host="+k,"nodename="+hostname
                print metric13,tx_drop,"interface="+interface,"host="+k,"nodename="+hostname
                metrics.send(metric1, round(docker_cpu_percent,3),host=k,nodename=hostname)
                print metric1,round(docker_cpu_percent,3),"host="+k,"nodename="+hostname
                metrics.send(metric2,mem_usage,host=k,nodename=hostname)
                print metric2,mem_usage,"host="+k,"nodename="+hostname
                metrics.send(metric9,mem_free,host=k,nodename=hostname)
                print metric9,mem_free,"host="+k,"nodename="+hostname
                metrics.send(metric3,max_mem,host=k,nodename=hostname)
                print metric3,max_mem,"host="+k,"nodename="+hostname
                metrics.send(metric4,round(docker_mem_percent,3),host=k,nodename=hostname)
                print metric4,round(docker_mem_percent,3),"host="+k,"nodename="+hostname
                metrics.send(metric7,docker_io_read,host=k,nodename=hostname)
                print metric7,docker_io_read,"host="+k,"nodename="+hostname
                metrics.send(metric8,docker_io_write,host=k,nodename=hostname)
                print metric8,docker_io_write,"host="+k,"nodename="+hostname

        print "======================================================================================================="
     except Exception ,e :
                print "Exception:",e,"At Line Number {}".format(sys.exc_info()[-1].tb_lineno)
     #time.sleep(interval)

if __name__ == "__main__":
     try:
         f = open('config.yml', 'r')
         config = yaml.load(f)
         main(config)
     except Exception ,e :
        print "Exception:",e,"At Line Number {}".format(sys.exc_info()[-1].tb_lineno)
	

