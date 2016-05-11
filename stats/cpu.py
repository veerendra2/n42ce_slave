import os
import pprint
import subprocess
import sys
import re
import json
import yaml
import potsdb,sys,linecache,time,math
from string import rstrip

'''
root@ubuntu:~# cat /proc/meminfo
MemTotal:        1008644 kB
'''
def proc_meminfo_parse(parse_this):
        meminfo_dict = {}
        for line in parse_this :
                line = line.split(":")
                key = line[0]
                value = int(line[1].strip().split()[0])
                meminfo_dict[key] = value
        return meminfo_dict

'''
root@ubuntu:~# cat /proc/stat
cpu  62774 0 41201 1714820 5377 3 1888 0 0 0
'''
def cpu(file_path):
        #file_path = '/proc/stat'
        line = open(file_path, 'r').readline()
        line = line.split()
        user = float(line[1])
        system = float(line[3])
        idle = float(line[4])
        iowait = float(line[5])
        return {"user":user,"system":system,"idle":idle,"iowait":iowait}
'''
root@ubuntu:~# cat /proc/diskstats
   8       0 sda 16037 1849 811046 1118700 20922 26340 6701584 552156 0 116520 1671328
'''
def diskstats_parse(dev,file_path):
    #file_path = '/proc/diskstats'
    result = {}

    # ref: http://lxr.osuosl.org/source/Documentation/iostats.txt
    columns_disk = ['m', 'mm', 'dev', 'reads', 'rd_mrg', 'rd_sectors',
                    'ms_reading', 'writes', 'wr_mrg', 'wr_sectors',
                    'ms_writing', 'cur_ios', 'ms_doing_io', 'ms_weighted']

    columns_partition = ['m', 'mm', 'dev', 'reads', 'rd_sectors', 'writes', 'wr_sectors']

    lines = open(file_path, 'r').readlines()
    for line in lines:
        #print line
        if line == '': continue
        split = line.split()
        if len(split) == len(columns_disk):
            columns = columns_disk
        elif len(split) == len(columns_partition):
            columns = columns_partition
        else:
            # No match
            continue

        data = dict(zip(columns, split))
        #print data
        if data['dev']  not in dev :
            continue
        #print data
        for key in data:
            if key != 'dev':
                data[key] = int(data[key])
        result[data['dev']] = data

    return result
def cpu_loadavg(file_path):
        #file_path = '/proc/loadavg'
        line = open(file_path, 'r').readline()
        #print line
        line = line.split()
        return {"one_m":float(line[0]),"five_m":float(line[1]),"fifteen_m":float(line[2])}

'''
root@ubuntu:~# df -h
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        19G  7.0G   11G  40% /
none            4.0K     0  4.0K   0% /sys/fs/cgroup
'''
def df_parse(parse_this,disk_r):
   for line in parse_this:
     line = line.split()
     if line[5] == disk_r:
        df_dict = {'system.disk.total':float(line[1]),'system.disk.used':float(line[2]),'system.disk.free':float(line[3]),'system.disk.util':float(line[4].split("%")[0])}
        return df_dict
	
def main(config):
    try:
	tsdbIp = config['tsdb']['tsdbIp']
        tsdbPort = config['tsdb']['tsdbPort']
        hostname = config['node_config_files']['host']
	#tsdb
        metrics = potsdb.Client(tsdbIp, port=tsdbPort,qsize=1000, host_tag=True, mps=100, check_host=True)
        #cpu
	f_c = cpu(config['node_config_files']['cpu_stats'])
	time.sleep(1)
	s_c = cpu(config['node_config_files']['cpu_stats'])
	cpu_r = {}
	for key in s_c:
		cpu_r[key] = s_c[key] - f_c[key]
	for key in cpu_r:
		k = "proc.cpu."+key
                metrics.send(k,cpu_r[key],host=hostname)
		print k,cpu_r[key],"host=",hostname
	print "proc.cpu.util ",(cpu_r['user']+cpu_r['system']),"host=",hostname
	metrics.send("proc.cpu.util",(cpu_r['user']+cpu_r['system']),host=hostname)
	loadavg = cpu_loadavg(config['node_config_files']['cpu_load'])
	for key in loadavg:
		k = "system.load."+key
		print k,loadavg[key],"host="+hostname
		metrics.send(k,loadavg[key],host=hostname)
        #memory
        mem_file = config['node_config_files']['memory']
        meminfo = open(mem_file,"r");
        meminfo_dict = proc_meminfo_parse(meminfo)
        systemmemfree = meminfo_dict['MemFree']/(2**10)
        systemmembuffered = meminfo_dict['Buffers']/2**10
        systemmemcached = meminfo_dict['Cached']/2**10
        systemmemtotal = meminfo_dict['MemTotal']/2**10
        systemmemshared = meminfo_dict['SwapCached']/2**10
        systemmemused = (meminfo_dict['MemTotal'] - meminfo_dict['MemFree'])/2**10
        systemmemutil = (systemmemused*100)/systemmemtotal
        mem_dict = {'system.mem.free':systemmemfree,'system.mem.buffered':systemmembuffered,'system.mem.cached':systemmemcached,'system.mem.total':systemmemtotal,'system.mem.shared':systemmemshared,'system.mem.used':systemmemused,'mem.usage.percent':systemmemutil}
        for k,v in mem_dict.iteritems():
                metrics.send(k,v,host=hostname)
                print k,v,"host=",hostname
        #disk
	f_d = diskstats_parse(["sda"],config['node_config_files']['disk'])
	time.sleep(1)	
	s_d = diskstats_parse(["sda"],config['node_config_files']['disk'])
	for dev in s_d :
		reads = (s_d[dev]['reads'] - f_d[dev]['reads'])
                writes = (s_d[dev]['writes'] - f_d[dev]['writes'])
                rd_sectors = (s_d[dev]['rd_sectors'] - f_d[dev]['rd_sectors'])*512
                wr_sectors = (s_d[dev]['wr_sectors'] - f_d[dev]['wr_sectors'])*512
		metrics.send("system.io.reads",reads,device=s_d[dev]['dev'],host=hostname)
		metrics.send("system.io.writes",writes,device=s_d[dev]['dev'],host=hostname)
                metrics.send("system.io.rb_s",rd_sectors,device=s_d[dev]['dev'],host=hostname)
                metrics.send("system.io.wb_s",wr_sectors,device=s_d[dev]['dev'],host=hostname)
                print "system.io.reads",reads,"device=",s_d[dev]['dev'],"host="+hostname #read requests issued to the device per second
		print "system.io.writes",writes,"device=",s_d[dev]['dev'],"host="+hostname #write requests issued to the device per second
		print "system.io.rb_s",rd_sectors,"device=",s_d[dev]['dev'],"host="+hostname # bytes reads to the device per second
		print "system.io.wb_s",wr_sectors,"device=",s_d[dev]['dev'],"host="+hostname # bytes  writes to the device per second
	
        #disk
        df = subprocess.check_output(['df','-m']).split('\n');
	disk_root = config['node_config_files']['disk_root']
        df_dict = df_parse(df,disk_root)
        for k,v in df_dict.iteritems():
                metrics.send(k,v,host=hostname)
                print k,v,"host=",hostname,"directory=root"
	


        metrics.wait()
        print "========= cpu %(except cpu.numprocesswaiting int), disk MB(except disk.utill %) ,mem MB ,disk.blocks.read/write(blocks/s) ======="
    except Exception ,e :
        print "Exception:",e,"At Line Number {}".format(sys.exc_info()[-1].tb_lineno)


if __name__ == "__main__":
     try:
	 f = open('config.yml', 'r')
         config = yaml.load(f)
         main(config)
     except Exception ,e :
	print "Exception:",e,"At Line Number {}".format(sys.exc_info()[-1].tb_lineno)
     
