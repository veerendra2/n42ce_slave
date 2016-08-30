'''
Author: Networks42
Description: Finds Dependencies between the docker containers
'''
import os,subprocess,time,json,redis,ast,traceback
import requests,datetime
import netifaces
import docker
import pynetfilter_conntrack
from pybrctl import BridgeController
#Local Imports
import port_dictionary

hostname=os.uname()[1]
base_path=os.path.dirname(os.path.abspath(__file__))
tenant_name="Carbon"  #os.environ['key']
interface_ip_list=list()
bridges_ip=list()
local_container_data=dict()
host_dicts=dict()#{<Interface_IP>-<MAP-Port>:[ip,cid,cname,]}
docker_info=list()

config = {'host': '52.8.104.253', 'port': 6379, 'db': 0}
headers = {'content-type': 'application/json'}
info_url="http://52.8.104.253:8161/n42-services/resources/appdiscovery/updateContainerDetails"
delete_url="http://52.8.104.253:8161/n42-services/resources/appdiscovery/deleteContainerDetails"
dependency_url="http://52.8.104.253:8161/n42-services/resources/appdiscovery/updateContainerDependency"
event_dictionary={"start":"started","stop":"stopped"}
listen_events = ["start","stop"]

files={"tcp_stats":"/proc/net/tcp",
       "docker-info":"/var/lib/docker/containers/{}/config.v2.json",
       "containers":"/var/lib/docker/containers"}

def execuite_cmd(cmd):
    return subprocess.check_output(cmd,shell=True)

def wipe_varibles():
    global docker_info,host_dicts,local_container_data,bridges_ip,interface_ip_list
    interface_ip_list=[]
    bridges_ip=[]
    local_container_data.clear()
    host_dicts.clear()
    docker_info=[]

def merge_dicts(*dict_args):
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result

def set_interface_ips():
    global interface_ip_list, bridges_ip
    brctl = BridgeController()
    bridge_iface=list()
    _bridge_names=list()
    for iface in brctl.showall():
        _bridge_names=str(iface)
        bridges_ip.append(netifaces.ifaddresses(str(iface))[2][0]["addr"])
    for iface1 in netifaces.interfaces():
        iface_atri=netifaces.ifaddresses(iface1).keys()
        if iface1 not in _bridge_names and 2 in iface_atri:
            interface_ip_list.append(netifaces.ifaddresses(iface1)[2][0]["addr"])
        
def get_service(port_list,label):
    try:
        if label:
            return label["service"]
    except Exception:
        if port_list and  port_list[0]["actual-port"] in port_dictionary.port_dict:
            return port_dictionary.port_dict[port_list[0]["actual-port"]]
        else:
            return "unknown"

def set_docker_info():
    global interface_ip_list, host_dicts, local_container_data, docker_info
    global_container_data=dict()
    container_id=os.listdir(files["containers"])# Get the List of Container IDS
    for ids in container_id: #Iter the CID to get container details
        if ids:
            port_list=list()
            try:
                f=open(files["docker-info"].format(ids),'r')
            except Exception:
                continue
            data = json.load(f)
            if data["State"]["Running"]:
                ip_addresses=list()
                for key,value in data["NetworkSettings"]["Ports"].items():
                    ip=[data["NetworkSettings"]["Networks"][a]["IPAddress"] for a in data["NetworkSettings"]["Networks"]]
                    if not value:
                        continue
                    for ports in value:
                        if ports["HostIp"]=="0.0.0.0":
                            for ips in interface_ip_list:
                                global_container_data[ips+":"+ports["HostPort"]]={"cid":ids[:12],"port":key.split("/")[0],"cname":data["Name"].lstrip("/"),"ip":ip,"hostname":hostname}
                        else:
                            global_container_data[ports["HostIp"]+":"+ports["HostPort"]]={"cid":ids[:12],"port":key.split("/")[0],"cname":data["Name"].lstrip("/")}
                        port_list.append({"map-port":ports["HostPort"],"actual-port":key.split("/")[0]})
                for v1 in data["NetworkSettings"]["Networks"].values():
                    local_container_data[v1["IPAddress"]]=[port_list,ids[:12],data["Name"].lstrip("/")]
                    ip_addresses.append(v1["IPAddress"])
                service_name=get_service(port_list,data["Config"]["Labels"])
                docker_info.append({"cid":ids[:12],"cname":data["Name"].lstrip("/"),"hostname":hostname,"pid":data["State"]["Pid"],"ip":ip_addresses,"image":data["Config"]["Image"],"Tenant_Name":tenant_name,"labels":data["Config"]["Labels"],"service":service_name})
    json_data=json.dumps(docker_info)              
    r = redis.StrictRedis(**config)
    r.hset(tenant_name+"-info",hostname,global_container_data)
    cluster_info=r.hgetall(tenant_name+"-info")
    print "+++++++++++++++++++++++"
    print global_container_data
    print "***********************"
    print cluster_info
    print "***********************"
    for x in cluster_info.values():
        host_dicts.update(ast.literal_eval(x))
    print "=================== Docker Info ===================\n"
    print json_data
    response = requests.post(info_url, data=json_data,headers=headers)
    print response,"\n"
  
def analyse_traffic():
    global host_dicts,local_container_data
    neighbors=set()
    container_in_dep=set()
    file=execuite_cmd("conntrack -L -p tcp | grep -v UNREPLIED |grep 'TIME_WAIT\|ESTABLISHED\|CLOSE'")
    for line in file.split("\n"):
        if line and "127.0.0.1" not in line and "tcp" in line:
            line_list= line.split()
            src_ip1=line_list[4].split("=")[1]
            dst_ip1=line_list[5].split("=")[1]
            #src_port1=line_list[6].split("=")[1]
            dst_port1=line_list[7].split("=")[1]
            
            src_ip2=line_list[8].split("=")[1]
            dst_ip2=line_list[9].split("=")[1]
            #src_port2=line_list[10].split("=")[1]
            #dst_port2=line_list[11].split("=")[1]
            if src_ip1 in bridges_ip and dst_ip2 in bridges_ip:
                continue #Packets coming from docker0(Default Gateway)
            elif dst_ip1+":"+dst_port1 in host_dicts and src_ip1 in local_container_data:
                if src_ip1 in local_container_data and dst_ip1+":"+dst_port1 in host_dicts:
                    src_con=local_container_data[src_ip1][1]
                    dst_con=host_dicts[dst_ip1+":"+dst_port1]["cid"]
                    port=host_dicts[dst_ip1+":"+dst_port1]["port"]
                    if port in port_dictionary.port_dict:
                        service=port_dictionary.port_dict[port]
                    else:
                        service="Unknown:{0}".format(port)
                    neighbors.add(src_con+"-"+dst_con+"-"+service)         
            
            elif src_ip1 in local_container_data and dst_ip1 in local_container_data:
                if src_ip1 in local_container_data and dst_ip1 in local_container_data:
                    src_con=local_container_data[src_ip1][1]
                    dst_con=local_container_data[dst_ip1][1]
                    if dst_port1 in port_dictionary.port_dict:
                        service=port_dictionary.port_dict[dst_port1]
                    else:
                        service="Unknown:{0}".format(port)
                    neighbors.add(src_con+"-"+dst_con+"-"+service)
            elif dst_ip1+":"+dst_port1 in host_dicts and src_ip1 not in local_container_data:
                if src_ip2 in local_container_data:
                    src_con="UNKNOWN"
                    dst_con=host_dicts[dst_ip1+":"+dst_port1]["cid"]
                    port=host_dicts[dst_ip1+":"+dst_port1]["port"]
                    if port in port_dictionary.port_dict:
                        service=port_dictionary.port_dict[port]
                    else:
                        service="Unknown:{0}".format(port)
                    neighbors.add(src_con+"-"+dst_con+"-"+service)
                           
    dependency=list()
    for key in neighbors:
        part=key.split("-")
        container_in_dep.add(part[0])
        container_in_dep.add(part[1])
        data={"srcvm":part[0],
              "dstvm":part[1],
              "dstservice":part[2],
              "srctenant":tenant_name,
              "dsttenant":tenant_name}
        dependency.append(data)
    return [dependency,container_in_dep]
    
def find_new_flow(cid):
    set_docker_info()
    counter=5
    while counter>=1:
        time.sleep(20)
        dep=analyse_traffic()
        if cid in dep[1]:
            print "Found new container's traffic :-)\n" 
            json_data=json.dumps(dep[0])
            response = requests.post(dependency_url, data=json_data,headers=headers)
            print "=================== Docker Dependencies ===================\n"
            print json_data
            print response
            return
        counter=counter-1
        print "Still not found any new Container"

def swarm_events():
    set_interface_ips()
    cli=docker.Client("0.0.0.0:4342")
    events = cli.events(decode=True)
    print "Listening to Docker events on the port: 4342"
    for event in events:
        try:
            if str(event['Action']) == "start":
                print str(str(event['Actor']['Attributes']['name'])),"launched!"
                find_new_flow(str(event['id'][:12]))
                wipe_varibles()
            elif str(event["Action"]) == "stop":
                print str(str(event['Actor']['Attributes']['name'])),"stopped!"
                json_data=json.dumps({"id":str(event['id'][:12])})
                print json_data
                response = requests.post(delete_url, data=json_data,headers=headers)
                print response
                wipe_varibles()
                print "Completed at",datetime.datetime.now()
        except:
            print "================ Something Went Wrong. TRACEBACK BELOW ================\n"
            print traceback.format_exc()
            print "-TIMESTAMP",datetime.datetime.now()
                   
if __name__ == '__main__':
    swarm_events()

