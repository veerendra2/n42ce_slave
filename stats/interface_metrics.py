import os
import pprint
import subprocess
import sys
import re
import json,yaml
import potsdb,sys,linecache,time,math
from string import rstrip
in_statictics = {}

'''
root@ubuntu:~# cat /proc/net/dev
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
  eth0: 140792077  239476    0    0    0     0          0         0 145515280  146321    0    0    0     0       0          0
docker0:       0       0    0    0    0     0          0         0        0       0    0    0    0     0       0          0
  eth1:  144464     854    0    0    0     0          0         0     5754      32    0    0    0     0       0          0
    lo: 8933788   35373    0    0    0     0          0         0  8933788   35373    0    0    0     0       0          0
'''
def proc_net_dev_parse(parse_this):
        interfaces_dict = {}
        for line in parse_this :
                if re.search('Receive|packets|qvb|qvo|qbr|ovs-system|br-tun|br-int|lo|veth|docker|flannel|virbr|br-', line) or  line == "":
                        continue
                line = line.strip()
                data = line.split(":")
                interface = data[0]
                in_data = data[1].strip().split()
                interfaces_dict[interface]={'rbytes':in_data[0],'rerrs':in_data[2],'rdrop':in_data[3],'tbytes':in_data[8],'terrs':in_data[10],'tdrop':in_data[11]}
        return interfaces_dict


def difference(list_1,list_2):
        global in_statictics
        for k,v in list_1.iteritems():
                in_statictics[k] = {'rbytes':(int(list_2[k]['rbytes']) - int(list_1[k]['rbytes']))/3,'rerrs':(int(list_2[k]['rerrs']) - int(list_1[k]['rerrs']))/3,'rdrop':(int(list_2[k]['rdrop']) - int(list_1[k]['rdrop']))/3,'tbytes':(int(list_2[k]['tbytes']) - int(list_1[k]['tbytes']))/3,'terrs':(int(list_2[k]['terrs']) - int(list_1[k]['terrs']))/3,'tdrop':(int(list_2[k]['tdrop']) - int(list_1[k]['tdrop']))/3}
        return  in_statictics
def calculate(Bytes):
        d = {}
        return {'v':float(Bytes)/(2**10),'type':"kB/s"}

def transferrate():
        global in_statictics
        for k,v in in_statictics.iteritems():
                r1 = calculate(v['rbytes'])
                t1 = calculate(v['tbytes'])
                in_statictics[k]['rrate'] = r1['v']
                in_statictics[k]['trate'] = t1['v']#str(t1['v']) +" "+ t1['type']

def utilization(interface_f):
        global in_statictics
        speed = {}
        for k,v in in_statictics.iteritems():
		f = interface_f+k+"/speed"
		print f
		f_r =  open(f,"r")
		speed = int(f_r.read()) * (2**20)
		#print speed,type(speed)
                if speed != 0:
                        in_util = (float(in_statictics[k]['rbytes']*100))/speed
                        out_util = (float(in_statictics[k]['tbytes']*100))/speed
                        in_statictics[k]['rutil'] = round(in_util,4)
                        in_statictics[k]['tutil'] = round(out_util,4)
		else:
			print "interface speed  showing 0"

def main(config):
	tsdbIp = config['tsdb']['tsdbIp']
        tsdbPort = config['tsdb']['tsdbPort']
        hostname = config['node_config_files']['host']
	interfaes_statictics_file  = config['node_config_files']['network']
        interfaes_statictics_list_first = open(interfaes_statictics_file,"r")
        first = proc_net_dev_parse(interfaes_statictics_list_first)
	print first
        time.sleep(3)
        interfaes_statictics_list_second = open(interfaes_statictics_file,"r")
        second = proc_net_dev_parse(interfaes_statictics_list_second)
        difference(first,second)
        transferrate()
	interface_f =  config['node_config_files']['interface_speed']
        utilization(interface_f)
        if_metrics = {'rbytes':'system.net.bytes_rcvd','tbytes':'system.net.bytes_sent','rutil':'system.net.in_util','tutil':'system.net.out_util','rrate':'system.net.received_rate','trate':'system.net.transmit_rate','rerrs':'system.net.packets_in.error','terrs':'system.net.packets_out.error','rdrop':'system.net.packets_in.drops','tdrop':'system.net.packets_out.drops'}
        #print if_metrics,if_metrics['rbytes'],if_metrics["rbytes"]
        try:
        #tsdb
                metrics = potsdb.Client(tsdbIp, port=tsdbPort,qsize=1000, host_tag=True, mps=100, check_host=True)
                for k,v in in_statictics.iteritems():
                        for k1,v1 in v.iteritems():
                                metrics.send(if_metrics[k1],v1,interface=k,host=hostname)
                                print if_metrics[k1],v1,"interface=",k,"host=",hostname
                metrics.wait()
                print "========= drops   packets,error  int,util   %,rate  kB/s ======="
        except Exception ,e :
                print "Exception:",e,"At Line Number {}".format(sys.exc_info()[-1].tb_lineno)



if __name__ == "__main__":
     #try:
         f = open('config.yml', 'r')
	 config = yaml.load(f)
         main(config)
     #except Exception ,e :
      #  print "Exception:",e,"At Line Number {}".format(sys.exc_info()[-1].tb_lineno)
