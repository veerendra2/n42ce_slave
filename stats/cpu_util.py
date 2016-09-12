'''
Author: Networks42
Description: Retrives the CPU, Disk metrics
'''
import os
import subprocess
import potsdb
import time
import traceback

tsdbIp="52.8.104.253"
tsdbPort=4343
interval=3
hostname=os.uname()[1]
file_locations={"memory":"/n42/proc/meminfo",
                "cpu_stats":"/n42/proc/stat",
                "cpu_load":"/n42/proc/loadavg",
                "disk":"/n42/proc/diskstats",
                "disk_root":"/n42"
                }

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

def cpu(file_path):
    line = open(file_path, 'r').readline()
    line = line.split()
    user = float(line[1])
    system = float(line[3])
    idle = float(line[4])
    iowait = float(line[5])
    return {"user":user,"system":system,"idle":idle,"wait.io":iowait}
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
        if line == '': continue
        split = line.split()
        if len(split) == len(columns_disk):
            columns = columns_disk
        elif len(split) == len(columns_partition):
            columns = columns_partition
        else:
            continue
        data = dict(zip(columns, split))

        if data['dev']  not in dev :
            continue
        for key in data:
            if key != 'dev':
                data[key] = int(data[key])
        result[data['dev']] = data
    return result

def cpu_loadavg(file_path):
    line = open(file_path, 'r').readline()
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
            df_dict = {'system.disk.total':float(line[1]),'system.disk.used':float(line[2]),'system.disk.free':float(line[3]),'disk.usage.percent':float(line[4].split("%")[0])}
            return df_dict
    
def main():
    try:
        metrics = potsdb.Client(tsdbIp, port=tsdbPort,qsize=1000, host_tag=True, mps=100, check_host=True)
        #cpu
        f_c = cpu(file_locations["cpu_stats"])
        time.sleep(1)
        s_c = cpu(file_locations["cpu_stats"])
        cpu_r = {}
        for key in s_c:
            cpu_r[key] = s_c[key] - f_c[key]
        for key in cpu_r:
            k = "proc.cpu."+key
            metrics.send(k,cpu_r[key],host=hostname)
            print k,cpu_r[key],"host=",hostname
        print "proc.cpu.util ",(cpu_r['user']+cpu_r['system']),"host=",hostname
        metrics.send("proc.cpu.util",(cpu_r['user']+cpu_r['system']),host=hostname)
        loadavg = cpu_loadavg(file_locations['cpu_load'])
        for key in loadavg:
            k = "proc.cpu.load.avg."+key
            print k,loadavg[key],"host="+hostname
            metrics.send(k,loadavg[key],host=hostname)
        #memory
        mem_file = file_locations['memory']
        meminfo = open(mem_file,"r");
        meminfo_dict = proc_meminfo_parse(meminfo)
        systemmemfree = meminfo_dict['MemFree']/(2**10)
        systemmembuffered = meminfo_dict['Buffers']/2**10
        systemmemcached = meminfo_dict['Cached']/2**10
        systemmemtotal = meminfo_dict['MemTotal']/2**10
        systemmemshared = meminfo_dict['SwapCached']/2**10
        systemmemused = (meminfo_dict['MemTotal'] - meminfo_dict['MemFree'])/2**10
        systemmemutil = (systemmemused*100)/systemmemtotal
        mem_dict = {'mem.free':systemmemfree,'mem.buffered':systemmembuffered,'mem.cached':systemmemcached,'mem.total':systemmemtotal,'mem.shared':systemmemshared,'mem.used':systemmemused,'mem.usage.percent':systemmemutil}
        for k,v in mem_dict.iteritems():
            metrics.send(k,v,host=hostname)
            print k,v,"host=",hostname
        #disk
        f_d = diskstats_parse(["sda"],file_locations['disk'])
        time.sleep(1)    
        s_d = diskstats_parse(["sda"],file_locations['disk'])
        for dev in s_d :
            reads = (s_d[dev]['reads'] - f_d[dev]['reads'])
            writes = (s_d[dev]['writes'] - f_d[dev]['writes'])
            rd_sectors = (s_d[dev]['rd_sectors'] - f_d[dev]['rd_sectors'])*512
            wr_sectors = (s_d[dev]['wr_sectors'] - f_d[dev]['wr_sectors'])*512
            metrics.send("system.io.reads",reads,device=s_d[dev]['dev'],host=hostname)
            print "disk.block.read",reads,"device=",s_d[dev]['dev'],"host="+hostname #read requests issued to the device per second
            metrics.send("system.io.writes",writes,device=s_d[dev]['dev'],host=hostname)
            print "disk.block.write",writes,"device=",s_d[dev]['dev'],"host="+hostname #write requests issued to the device per second
            metrics.send("system.io.rb_s",rd_sectors,device=s_d[dev]['dev'],host=hostname)
            print "system.io.rb_s",rd_sectors,"device=",s_d[dev]['dev'],"host="+hostname # bytes reads to the device per second
            metrics.send("system.io.wb_s",wr_sectors,device=s_d[dev]['dev'],host=hostname)
            print "system.io.wb_s",wr_sectors,"device=",s_d[dev]['dev'],"host="+hostname # bytes  writes to the device per second
        #disk
        df = subprocess.check_output(['df','-m']).split('\n');
        disk_root = file_locations['disk_root']
        df_dict = df_parse(df,disk_root)
        for k,v in df_dict.iteritems():
            metrics.send(k,v,host=hostname)
            print k,v,"host=",hostname,"directory=root"
    
        metrics.wait()
        print "========= cpu %(except cpu.numprocesswaiting int), disk MB(except disk.utill %) ,mem MB ,disk.blocks.read/write(blocks/s) ======="
    except:
        print "================TRACKBACK================"
        traceback.format_exc()



     
