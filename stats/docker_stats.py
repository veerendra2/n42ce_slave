import os 
import linecache
import time
import potsdb
import json
import traceback

tsdbIp="52.8.104.253"
tsdbPort=4343
hostname=os.uname()[1]
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

file_locations={"host": "hostname",
                "memory": "/n42/proc/meminfo",
                "cpu_stats": "/n42/proc/stat",
                "cpu_load": "/n42/proc/loadavg",
                "disk": "/n42/proc/diskstats",
                "network": "/n42/proc/net/dev",
                "interface_speed": "/sys/class/net/",
                "proc": "/n42/proc/",
                "disk_root": "/n42",
                "config_json": "/config.v2.json"}

def get_containers():
    directory = "/sys/fs/cgroup/cpuacct/docker"
    return next(os.walk(directory))[1]

def read_file(file_name,line_no,split_no=None):
    if line_no is not None:
        value=linecache.getline(file_name, line_no)
        if value and not split_no:
            return value
        elif value and split_no:
            try:
                var=value.split()[split_no]
            except:
                var=0
            return var
        else:
            return 0
    else:
        l1=list()
        f=open(file_name,'r')
        lists=f.readlines()
        for a in lists[2:len(lists)-1]:
            l1.append(a)
        return l1

def get_all_values():
    values_dict = {}
    containers=get_containers()
    for c in containers:
        try:
            max_memory_f = "/sys/fs/cgroup/memory/docker/{}/memory.limit_in_bytes".format(c)
            usage_memory_f = "/sys/fs/cgroup/memory/docker/{0}/memory.usage_in_bytes".format(c)
            docker_mem_stat_f  = "/sys/fs/cgroup/memory/docker/{}/memory.stat".format(c)
            docker_cpu_f = "/sys/fs/cgroup/cpuacct/docker/{}/cpuacct.usage".format(c)
            sys_cpu_f = file_locations["cpu_stats"]#"/proc/stat"
            docker_io_f = "/sys/fs/cgroup/blkio/docker/{}/blkio.throttle.io_service_bytes".format(c)
            container_pid_f = "/var/lib/docker/containers/{}/config.v2.json".format(c)
            max_memory = int(read_file(max_memory_f,1))
            usage_memory = int(read_file(usage_memory_f,1))
            docker_pagefults =  read_file(docker_mem_stat_f,10)
            docker_rss =  read_file(docker_mem_stat_f,19)
            docker_cpu = int(read_file(docker_cpu_f,1))
            sys_cpu_l = read_file(sys_cpu_f,1).split()
            sys_cpu = 0
            for i in sys_cpu_l[1:]:
                sys_cpu = sys_cpu + int(i)
            docker_io_read = float(read_file(docker_io_f,1,2))
            docker_io_write = float(read_file(docker_io_f,2,2))

            container_pid = open(container_pid_f,'r')
            j=json.load(container_pid)
            docker_net_f = file_locations["proc"]+ str(j['State']['Pid'])+"/net/dev"
            v = read_file(docker_net_f,None)[0].split()
            values_dict[c[:12]] = {'max_memory':max_memory,'usage_memory':usage_memory,'docker_cpu':docker_cpu,'sys_cpu':sys_cpu,'docker_io_read':docker_io_read,'docker_io_write':docker_io_write,'docker_pagefults':docker_pagefults,'docker_rss':docker_rss,'intface_stat':v}
        except:
            print "===============TRACEBACK==================="
            print traceback.format_exc()
            continue

    linecache.clearcache()
    return values_dict


def main():
    host_mem_size = round((float(read_file(file_locations['memory'],1,1)))/(2**10),3)
    try:
        sleeptime = 3
        a = get_all_values()
        time.sleep(sleeptime)
        b = get_all_values()
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
    except:
        print "=============TRACKBACK============="
        print traceback.format_exc() 

