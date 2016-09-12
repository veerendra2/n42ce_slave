import cpu_util
import docker_stats
import time
import traceback

while True:
    try:
        cpu_util.main()
        docker_stats.main()
        time.sleep(3)
    except Exception ,e :
        print "=========TRACEBACK-MAIN========="
        print traceback.format_exc()
