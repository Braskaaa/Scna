import subprocess
import random
import os
import sys
import socket
import re
from termcolor import colored


def search1(file):
     while True:
        with open(os.devnull, "wb") as limbo:
            ping01 = random.randint(0, 255)
            ping02 = random.randint(0, 255)
            ping03 = random.randint(0, 255)
            ping04 = random.randint(0, 255)
            ip = str(ping04) + "." + str(ping01) + "." + str(ping02) + "." + str(ping03)
            result = subprocess.Popen(["ping", "-c", "1", "-n", "-W", "2", ip],
                                         stdout=limbo, stderr=limbo).wait()
            if result:
                print ip, "inactive"
            else:
                print colored(ip, 'green'), colored("active", 'green')
                logs = open('ip.log', 'a')
                logs.write(ip + "\n")

def search(file):

    while True:

        ping01 = random.randint(0, 255)
        ping02 = random.randint(0, 255)
        ping03 = random.randint(0, 255)
        ping04 = random.randint(0, 255)

        ip = str(ping04) + "." + str(ping01) + "." + str(ping02) + "." + str(ping03)
        port = 23
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((ip, port))
        if result == 0:
            print colored("23 PORT open on %s", "green") % ip
            logs = open(file, 'a')
            logs.write(ip + "\n")
        else:
            print colored("23 PORT CLOSED on %s", 'red') % ip



def port(inputfile):
    with open(inputfile) as f:
        for ip in f:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((ip, 23))
            if result == 0:
                print colored("port open on %s", "green") % ip
            else:
                print colored("PORT closed on %s", 'red')  % ip


if __name__ == "__main__":

    type =  str(sys.argv[1])
    file = str(sys.argv[2])
    print type, file
    if type == '-FULL':
        search(file)
    elif type == "-Ps":
        port(file)
    elif type == "-PIs":
        search1(file)
    else:
        pass
#    except:
 #       print "Usage: -FULL <outputfile>"
  #      print "       -Ps <inputfile>"



