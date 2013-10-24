# jsb/plugs/myplugs/socket/lights.py
#
# Author: Petraea
#

from jsb.lib.commands import cmnds
from jsb.lib.examples import examples
from jsb.lib.persist import PlugPersist

import select, sys, os, time, string
import socket, logging

LIGHTSERVER = ('lanbox.nurdspace.lan', 777)
LIGHTSERVER_PASSWORD='777\n'

light_data = PlugPersist('light_data')
light_aliases = PlugPersist('light_aliases')
light_profiles = PlugPersist('light_profiles')

FLUORO = {'channel':9,'channels':4}

#Custom error for parser
class ParseError(Exception):
    pass

def split_by_n( seq, n ):
    while seq:
        yield seq[:n]
        seq = seq[n:]

def list_range(l):
    tmp = l[:] #Take a copy of the list
    tmp.sort()
    start = tmp[0]
    currentrange = [start, 1]
    currentnext = start+1
    for item in tmp[1:]:
        if currentnext == item:
            currentnext += 1
            currentrange[1] += 1
        else:
            yield tuple(currentrange)
            currentnext = item+1
            currentrange = [item, 1]
    yield tuple(currentrange)

def Table1(response='',model = ''): #What model am I from response, or, what response would give this model?
    T1 = {'LC+':'F8FB','LCX':'F8FD','LXM':'F8FF','LCE':'F901'}
    rT1 = {value: key for key, value in T1.items()}
    if response is not '':
        m = 'unknown'
        for model in T1:
            if T1[model] == response:
                m = model
        return m
    if model is not '':
        r = ''
        for response in rT1:
            if T1[response] == model:
                r = response
        return r
    
  
def Table2(model, device): #Does this model LanBox have this device, and if so what's the channel?
    T2 = {'LCX':{'mixer':'FE','dmxout':'FF','dmxin':'FC','externalinputs':'FD'},
          'LCE':{'mixer':'FE','dmxout':'FF','dmxin':'FC','externalinputs':'FD'},
          'LCM':{'mixer':'FE','dmxout':'FF'},
          'LC+':{'mixer':'09','dmxout':'0A'}}
    ret = {}
    try:
        mtable = T2[model]
        ret = mtable[device]
    except:
        pass
    return ret
    
def Table3(response = '', status = []): #What is the status list of this channel, or, what would give this status from a list?
    T3 = {0:'mixstatus',1:'channeleditstatus',2:'solostatus',3:'fadestatus'}
    rT3 = {value: key for key, value in T3.items()}
    if response is not '':
        ret = []
        bits = bin(response)[2:]
        try:
            for bit in T3:
                if bits[-bit-1] == '1':
                    ret.append(T3[bit])
            return ret
        except:
            return
    if status is not []:
        ret = '0000'
        for s in status:
            if s.lower() in rT3:
               ret[3-rT3[s.lower()]]='1'
        return ret
    
def Table4(response='', flags = []): #What is the attribute flags list for this layer, or, what would give this flag list?
    T4 = {0:'layeroutputenabled',1:'sequencemode',2:'fadestatus',3:'solostatus',4:'pausestatus',5:'auto',6:'sequencerwaiting',7:'locked'}
    rT4 = {value: key for key, value in T4.items()}
    if response is not '':
        ret = []
        bits = bin(response)[2:]
        try:
            for bit in T4:
                if bits[-bit-1] == '1':
                    ret.append(T4[bit])
            return ret
        except:
            return
    if flags is not []:
        ret = '00000000'
        for f in flags:
            if f.lower() in rT4:
               ret[7-rT4[f.lower()]]='1'
        return ret

def Table5(response = '', mode = ''): #What is the mix mode of this layer, or, what would I need to set to have this mix mode?
    T5 = {'0':'off','1':'copy','2':'htp','3':'ltp','4':'transparent','5':'add'}
    rT5 = {value: key for key, value in T5.items()}
    if response is not '':
        response = str(response).lstrip('0')
        mode = 'unknown'
        if response in T5:
            type = T5[response]
        return mode
    if mode is not '':
        ret = ''
        if mode.lower() in rT5:
            ret = rT5[mode.lower()].zfill(2)
        return ret

def Table6(response = '', mode = ''): #What is the chase mode of this layer, or, what would I need to set to have this chase mode?
    T6={'0':'off','1':'chaseup','2':'loopup','3':'chasedown','4':'loopdown','5':'random',
    '6':'looprandom','7':'bounce','8':'loopbounce'}
    rT6 = {value: key for key, value in T6.items()}
    if response is not '':
        response = str(response).lstrip('0')
        mode = 'unknown'
        if response in T6:
            type = T6[response]
        return mode
    if mode is not '':
        ret = ''
        if mode.lower() in rT6:
            ret = rT6[mode.lower()].zfill(2)
        return ret

def Table7(response = '', mode = ''): #What is the fade mode of this layer, or, what would I need to set to have this fade mode?
    T7={'0':'off','1':'fadein','2':'fadeout','3':'crossfade','4':'off','5':'fadeincr',
    '6':'fadeoutcr','7':'crossfadecr'}
    rT7 = {value: key for key, value in T7.items()}
    if response is not '':
        response = str(response).lstrip('0')
        mode = 'unknown'
        if response in T7:
            type = T7[response]
        return mode
    if mode is not '':
        ret = ''
        if mode.lower() in rT7:
            ret = rT7[mode.lower()].zfill(2)
        return ret

def Table8(response = '', speed = ''): #What baud rate am I, or, what baud rate would give this?
    T8 = {'0':'38400','1':'19200','2':'9600','3':'31250'}
    rT8 = {value: key for key, value in T8.items()}
    if response is not '':
        response = str(response).lstrip('0')
        speed = ''
        if response in T8:
            speed = T8[response]
        return speed
    if speed is not '':
        ret = ''
        if speed in rT8:
            ret = rT8[speed].zfill(2)
        return ret
    
    
def Table9(response = '', output = []): #what UDP output am I, or, what would I do for this?
    T9 = {0:'broadcastdmxout',1:'broadcastmixerchannels',2:'broadcastexternalinputvalues',
    3:'broadcastdmxin',4:'broadcastlayerlist',5:'synchronizelayers'}
    rT9 = {value: key for key, value in T9.items()}
    if response is not '':
        ret = []
        bits = bin(response)[2:]
        try:
            for bit in T9:
                if bits[-bit-1] == '1':
                    ret.append(T9[bit])
            return ret
        except:
            return
    if output is not []:
        ret = '00000000'
        for f in output:
            if f.lower() in rT4:
               ret[7-rT4[f.lower()]]='1'
        return ret
    
def Table10(secs): #Give me the right format to update the clock
    offset = int(secs) + 335361600
    return hex(offset)[2:].zfill(8)
        
    
def AppendixA(response = '', secs = ''): #Convert a fade duration to a time, or, convert a duration to the closest time available.
    ApA = [0,0.05,0.1,0.15,0.2,0.25,0.3,0.25,0.4,0.45,0.5,0.55,0.6,0.65,0.7,0.75,
    0.8,0.85,0.9,0.95,1,1.1,1.2,1.3,1.5,1.6,1.8,2.0,2.2,2.4,2.7,3,3.3,3.6,3.9,
    4.3,4.7,5.1,5.6,6.2,6.8,7.5,8.2,9.1,10,11,12,13,15,16,18,20,22,24,27,30,
    33,36,39,43,47,51,56,60,66,72,78,90,96,108,120,132,144,162,180,198,222,234,
    258,288,306,342,378,408,450,492,546,600,660,720,780,900,float('inf')]
    if response is not '':
        time = 0
        try:
            if int(response) in range(len(ApA)):
                time = ApA[int(response)]
            return time
        except:
            return
    if secs is not '':
        dur = float(secs)
        if dur != float('inf'):
            distance = abs(dur - ApA[0])
            ret = 0
            for n, v in enumerate(ApA[1:]):
                if abs(dur - v) < distance:
                    distance = abs(dur - v)
                    ret = n+1
                else:
                    continue
        else: ret = 92 #Don't mess if you're infinite; closest won't work
        return hex(ret)[2:].zfill(2)



def commentTranslate(response = '', comment = ''): #Decode a comment line, or, encode one
    commentchars = [' ','A','B','C','D','E','F','G','H','I','J','K','L','M','N','O',
    'P','Q','R','S','T','U','V','W','X','Y','Z','a','b','c','d','e','f','g','h','i',
    'j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z','0','1','2',
    '3','4','5','6','7','8','9','-']
    if response is not '':
        try:
            commentbytes = bin(response)[2:] #comes out as 0bAABB...
            out = ''
            for i in range(0,len(commentbytes)-5,6):
                out = out + commentchars[int(commentbytes[i:i+5],2)]
            return out
        except:
            return
    if comment is not '':
        comment = (str(comment)+'        ')[:7]
        response = ''
        for letter in comment:
            for n, c in enumerate(commentchars):
                if c == letter:
                    response = response + bin(n)[2:].zfill(6) #ABCDEF ABCD...
        return hex(int(response,2))[2:]

def chaseSpeed(response = '', speed = ''): #Decode a chase speed response, or encode one
    if response is not '':
        return 12800/(255-int(response,16))
    if speed is not '':
        s = int(speed)
        if s <= 50.1: s = 50.1
        return hex(255-int(12800/s))[2:].zfill(2)


def AppendixB(response = '', stepstocode = {}): #Decode a stepdata string, or, encode one!
    stepdata={1:{'name':'showscene',1:'fadetype',2:'fadetime',3:'holdtime'},
    2:{'name':'showsceneofcuelist',1:'fadetype',2:'fadetime',3:'holdtime',4:'cuelist',6:'cuestep'}, 
    10:{'name':'gocuestepinlayer',1:'layerid',2:'cuelist',4:'cuestep'},
    11:{'name':'clearlayer',1:'layerid'},
    12:{'name':'pauselayer',1:'layerid'},
    13:{'name':'resumelayer',1:'layerid'},
    14:{'name':'startlayer',1:'layerid'},
    15:{'name':'stoplayer',1:'layerid'},
    16:{'name':'configurelayer',1:'sourcelayerid',2:'destlayerid',3:'newlayerid',4:'cuelist',5:'cuestep'},
    17:{'name':'stoplayer',1:'layerid'},
    18:{'name':'gotrigger',1:'layerid',2:'cuelist',3:'triggerid',4:'channel'},
    20:{'name':'gocuestep',1:'cuestep'},
    21:{'name':'gonextinlayer',1:'layerid'},
    22:{'name':'gopreviousinlayer',1:'layerid'},
    23:{'name':'looptocuestep',1:'cuestep',2:'numberofloops'},
    24:{'name':'hold',1:'holdtime'},
    25:{'name':'holduntil',1:'day',2:'hours',3:'minutes',4:'seconds',5:'frames'},
    26:{'name':'goifanaloguechannel',1:'analoguedata',6:'cuestep'},
    27:{'name':'goifchannel',1:'layerid',2:'channel',3:'govalues',5:'cuestep'},
    30:{'name':'setlayerattributes',1:'fadeenable',2:'outputenable',3:'soloenable',4:'lock'},
    31:{'name':'setlayermixmode',1:'layerid',2:'mixmode',3:'transparencydepth1',4:'transparencydepth2',5:'fadetime'},
    32:{'name':'setlayerchasemode',1:'layerid',2:'mixmode',3:'chasespeed1',4:'chasespeed2',5:'fadetime'},
    40:{'name':'writemidistream',1:'mididata'},
    49:{'name':'writeserialstream1',1:'serialdata'},
    50:{'name':'writeserialstream2',1:'serialdata'},
    51:{'name':'writeserialstream3',1:'serialdata'},
    52:{'name':'writeserialstream4',1:'serialdata'},
    53:{'name':'writeserialstream5',1:'serialdata'},
    54:{'name':'writeserialstream6',1:'serialdata'},
    55:{'name':'writeserialstream7',1:'serialdata'},
    56:{'name':'writeserialstream8',1:'serialdata'},
    70:{'name':'comment',1:'comment'}}
    if response is not '':
        ret = dict()
        type = int(data[0:2],16)
        if type in stepdata:
            steptype = stepdata[type]
            for value in steptype:
                if value == 'name':
                    ret['name'] = steptype['name']
                else:
                    datatype = steptype[value] #Where value = field number
                    if datatype == 'fadeenable' or datatype == 'outputenable' or datatype == 'soloenable' or datatype == 'lock': #Booleans
                        if response[2*value+1:2*value+2] is '00': ret[datatype]=False
                        else: ret[datatype]=True
                    elif datatype == 'fadetime' or datatype == 'holdtime' or datatype == 'fadetime': #Appendix A lookup
                        ret[datatype] = AppendixA(response[2*value+1:2*value+2])
                    elif datatype == 'channel' or datatype == 'govalues': #2-byte length
                        ret[datatype] = response[2*value+1:2*value+4]
                    elif datatype == 'mididata' or datatype =='analoguedata' or datatype == 'serialdata': #6-byte length
                        ret[datatype] = response[2*value+1:2*value+12]
                    elif datatype == 'transparencydepth1' or datatype == 'transparencydepth2': #100% = 255
                        ret[datatype] = str(int(response[2*value+1:2*value+2],16)*100/255)
                    elif datatype == 'chasespeed1' or datatype =='chasespeed2': #chaseSpeeds
                        ret[datatype] = chaseSpeed(response[2*value+1:2*value+2])
                    elif datatype == 'fadetype':
                        ret[datatype] = Table7(response[2*value+1:2*value+2])
                    elif datatype == 'mixmode':
                        ret[datatype] = Table5(response[2*value+1:2*value+2])
                    elif datatype == 'comment':
                        ret[datatype] = commentTranslate(response[2*value+1:2*value+12])
                    elif datatype == 'day':
                        d = response[2*value+1:2*value+2]
                        if d == '00': ret[datatype]='Mon'
                        if d == '01': ret[datatype]='Tue'
                        if d == '02': ret[datatype]='Wed'
                        if d == '03': ret[datatype]='Thu'
                        if d == '04': ret[datatype]='Fri'
                        if d == '05': ret[datatype]='Sat'
                        if d == '06': ret[datatype]='Sun'
                        if d == '80': ret[datatype]='ALL'
                    else:
                        ret[datatype] = response[2*value+1:2*value+2]
        return ret
    if stepstocode is not {}:
        returnlist = ['00','00','00','00','00','00','00']
        for steptype in stepdata:
            if stepstocode['name'].lower() == stepdata[steptype]['name']:
                returnlist[0]= hex(steptype)[2:].zfill(2)
                del stepstocode['name']
                for element in stepstocode:
                    for position in stepdata[steptype]:
                        if element.lower() == stepdata[steptype][position]:
                            payload = stepstocode[element]
                            if element == 'fadeenable' or element == 'outputenable' or element == 'soloenable' or element == 'lock': #Booleans
                                if payload is True:
                                    returnlist[position] = 'FF'
                                else: returnlist[position]='00'
                            elif element == 'fadetime' or element == 'holdtime': #Appendix A lookup
                                returnlist[position] = AppendixA('',payload)
                            elif element == 'channel' or element == 'govalues': #2-byte length
                                returnlist[position] = payload[0:2]
                                returnlist[position+1] = payload[2:4]
                            elif element == 'mididata' or element =='analoguedata' or element == 'serialdata': #6-byte length
                                returnlist[position] = payload[0:2]
                                returnlist[position+1] = payload[2:4]
                                returnlist[position+2] = payload[4:6]
                                returnlist[position+3] = payload[6:8]
                                returnlist[position+4] = payload[8:10]
                                returnlist[position+5] = payload[10:12]
                            elif element == 'transparencydepth1' or element == 'transparencydepth2': #100% = 255
                                try:
                                    percent = int(payload)
                                    if percent >100: percent = 100
                                    if percent <0: percent = 0
                                except:
                                    percent = 0
                                returnlist[position] = hex(int(payload)*255/100)[2:].zfill(2)
                            elif element == 'chasespeed1' or element =='chasespeed2': #chaseSpeeds
                                returnlist[position] = chaseSpeed('',payload)
                            elif element == 'fadetype':
                                returnlist[position] = Table7('',payload)
                            elif element == 'mixmode':
                                returnlist[position] = Table5('',payload)
                            elif element == 'comment':
                                returnlist[position] = commentTranslate('',payload)
                            elif element == 'day':
                                if payload.lower()[:3] == 'mon': returnlist[position] = '00'
                                if payload.lower()[:3] == 'tue': returnlist[position] = '01'
                                if payload.lower()[:3] == 'wed': returnlist[position] = '02'
                                if payload.lower()[:3] == 'thu': returnlist[position] = '03'
                                if payload.lower()[:3] == 'fri': returnlist[position] = '04'
                                if payload.lower()[:3] == 'sat': returnlist[position] = '05'
                                if payload.lower()[:3] == 'sun': returnlist[position] = '06'
                                if payload.lower()[:3] == 'all': returnlist[position] = '80'
                            else:
                                retlist[position]= hex(element)[2:].zfill(2)
                return ''.join(returnlist)
            else: pass

def layerInfo(layerstring):
    layerdata = {'outputstatus':('0>-','int','0','2'),
    'sequencestatus':('0>-','int','2','4'),
    'fadestatus':('0>-','int','4','6'),
    'solostatus':('0>-','int','6','8'),
    'mixstatus':('Table5','','8','10'),
    'currentholdtime':('AppendixA','','12','14'),
    'remainingholdtime':('0.05*','int','14','18'),
    'activecuelist':('','int','18','22'),
    'activecuestep':('','int','22','24'),
    'currentchasemode':('Table6','','24','26'),
    'currentlayerspeed':('chaseSpeed','int','26','28'),
    'manualfadetype':('Table7','','28','30'),
    'manualfadetime':('AppendixA','int','30','32'),
    'cuestepfadetime':('AppendixA','int','32','34'),
    'remainingfadetime':('0.05*','int','34','38'),
    'transparencydepth':('(100.0/255)*','int','38','40'),
    'loadingindication':('','int','40','42'),
    'pausestatus':('0>-','int','42','44'),
    'sysex':('','int','44','46'),
    'auto':('0>-','int','46','48'),
    'currentstep':('stepData','','48','62')}
    ret = dict()
    for value in layerdata:
        f1,f2,f,t = layerdata[value]
        if f2  == 'int':
            ret[value]=eval(f1+'('+f2+'('+'layerstring['+f+':'+t+'],16))')
        else:
            ret[value]=eval(f1+'('+f2+'('+'layerstring['+f+':'+t+']))')
    return ret

def crossfade(todict, time = 0.5, layer = 1):
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s = connectToLB(s)
    l = hex(layer)[2:].zfill(2)
    fromdict = {}
    for light in todict:
        c = hex(int(light))[2:].zfill(4)
        fromdict[light] = int(executeLB(s,'CD'+l+c+'01'),16)
    cueid = '0002'
    steps = '02'
    step1 = AppendixB('',{'name':'showscene','fadetype':'crossfade','fadetime':time,'holdtime':0})
    step2 = AppendixB('',{'name':'showscene','fadetype':'crossfade','fadetime':time,'holdtime':float('inf')})
    logging.warn(executeLB(s,'AA'+cueid+steps+step1+step2))
    numchans = hex(len(todict))[2:].zfill(4)
    enc = ''
    for light in fromdict:
        enc = enc + hex(int(light))[2:].zfill(4)
        enc = enc + hex(int(fromdict[light]))[2:].zfill(2)
    logging.warn(executeLB(s,'AC'+cueid+'01'+'00'+numchans+enc))
    enc = ''
    for light in todict:
        enc = enc + hex(int(light))[2:].zfill(4)
        enc = enc + hex(int(todict[light]))[2:].zfill(2)
    logging.warn(executeLB(s,'AC'+cueid+'02'+'00'+numchans+enc))
    
    logging.warn(executeLB(s,'56'+l+cueid))
    s.close()

def connectToLB(s):
    data = ''
    s.connect(LIGHTSERVER)
    data=s.recv(512)
    while data != 'connected':
        s.sendall(LIGHTSERVER_PASSWORD)
        data=s.recv(512)
    s.sendall('*6501#') #16 bit mode on
    data=s.recv(512)
    return s

def executeLB(s,command):
    s.sendall('*'+command+'#')
    ret = s.recv(512)
    if ret != '?':
        ret = ret[1:-2]
    return ret

def chan_toggle(chan,layer = 1):
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s = connectToLB(s)
    l = hex(layer)[2:].zfill(2)
    c = hex(chan)[2:].zfill(4)
    level = int(executeLB(s,'CD'+l+c+'01'),16)
    retval = (0,0,0)
    if level is not 0:
        executeLB(s,'C9'+l+c+'00')
        retval = (chan,layer,00)
    else:
        executeLB(s,'C9'+l+c+'FF')
        retval = (chan,layer,255)
    s.close()
    return retval

def chan_set(chan,level,layer = 1):
    if level<0: level = 0
    if level>255: level = 255
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s = connectToLB(s)
    l = hex(layer)[2:].zfill(2)
    c = hex(chan)[2:].zfill(4)
    v = hex(level)[2:].zfill(2)
    retval = (0,0,0)
    executeLB(s,'C9'+l+c+v)
    retval = (chan,layer,level)
    s.close()
    return retval

def chan_info(chan, channels=1,layer = 1):
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s = connectToLB(s)
    l = hex(layer)[2:].zfill(2)
    c = hex(chan)[2:].zfill(4)
    n = hex(channels)[2:].zfill(2)
    level = executeLB(s,'CD'+l+c+n)
    values = list(split_by_n(level,2))
    retval = (chan,layer,values)
    s.close()
    return retval

def token_parse(input, separator=',',equator='='):
    input += separator
    tdict = {}
    toassign = []
    token = ''
    assigning = False
    for c in input:
        if c == separator:
            token = token.strip()
            if token == '': raise ParseError("Tokens can't be blank.")
            if assigning:
                for i in toassign:
                    tdict[i.lower()]=token
                toassign = []
                assigning = False
                token = ''
            else:
                toassign.append(token)
                token = ''
        elif c == equator:
            token = token.strip()
            if not assigning:
                assigning = True
                toassign.append(token)
                token = ''
            else:
                raise ParseError("Two equals in a row?")
        else:
            token += c
    if assigning:
       raise ParseError("Parse Error")
    if token.strip() is not '':
        raise ParseError('Token still present.')
    if  len(toassign) != 0:
        for t in toassign:
            tdict[t] = '-9999'
    return tdict

def chan_multiset(lightdict,layer = 1):
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s = connectToLB(s)
    sendstring = hex(layer)[2:].zfill(2)
    for light in lightdict:
        if lightdict[light]<0: lightdict[light] = 0
        if lightdict[light]>255: lightdict[light] = 255
        sendstring += hex(int(light))[2:].zfill(4)
        sendstring += hex(int(lightdict[light]))[2:].zfill(2)
    executeLB(s,'C9'+sendstring)
    s.close()
    return lightdict

def chan_multiinfo(lightdict,layer = 1):
    l = hex(layer)[2:].zfill(2)
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s = connectToLB(s)
    lranges = list_range([int(x) for x in lightdict.keys()])
    retdict = {}
    for rangepair in lranges:
        rangestart = 0
        while rangestart<rangepair[1]: #Can only do 255 at once!
            currentrange = min(rangepair[1]-rangestart,255)
            lstr = l + hex(rangepair[0])[2:].zfill(4) + hex(currentrange)[2:].zfill(2)
            retlst = list(split_by_n(executeLB(s,'CD'+lstr),2))
            logging.warn(lstr)
            logging.warn(retlst)
            for i in range(rangestart,currentrange):
                retdict[i+rangepair[0]]=int(retlst[i],16)
            rangestart += currentrange
    s.close()
    return retdict

def flash():
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s = connectToLB(s)
    layer ='01'
    chanlist = list(split_by_n(executeLB(s,'CD'+layer+'0001'+'00'),2)) #Tell me all channel settings on layer 1
    sendstream = ''
    for i in range(1, len(chanlist)):
        sendstream += hex(i)[2:].zfill(4)
        sendstream += '00'
    executeLB(s,'C9'+layer+sendstream) #Set everything to off
    time.sleep(0.5)
    executeLB(s,'C9'+layer+'0006'+'FF') #Long niztest
    #executeLB(s,'C9'+layer+'0006'+'40') #Medium rate
    executeLB(s,'C9'+layer+'0005'+'C0') #Flash ON!
    time.sleep(1)
    sendstream = ''
    for i in range(1,len(chanlist)):
        sendstream += hex(i)[2:].zfill(4)
        sendstream += chanlist[i-1].zfill(2)
    executeLB(s,'C9'+layer+sendstream) #Restore
    s.close()

def handle_lightdata_add(bot, ievent):
    if not ievent.rest: ievent.missing('<light name> <channel1> <channel2> ...') ; return
    try:
        splitted_input = ievent.rest.split()
        lightname = splitted_input[0]
        channels = []
        for c in splitted_input[1:]:
            channels.append(int(c))
    except:
        ievent.reply('Incorrect Format.')
    ievent.reply('Saving: '+lightname+' channels ('+str(channels)+')')
    light_data.data[lightname.lower()] = channels
    light_data.save()

def handle_lightdata_del(bot, ievent):
    if not ievent.rest: ievent.missing('<light name>') ; return
    splitted_input = ievent.rest.split()
    lightname = splitted_input[0]
    try:
        del light_data.data[lightname]
        light_data.save()
    except: ievent.reply("no such light") ; return
    ievent.reply(lightname + " removed")

def handle_list_lightdata(bot, ievent):
    ievent.reply(str(light_data.data.items()))

def lightdata_lookup(token,assign,separator='-'):
    retdict = {}
    stoken = token.split(separator)
    lights = light_data.data
    if stoken[0].strip().lower() in lights:
        channels = lights[stoken[0].strip().lower()]
        if len(stoken)==2:
            offset = int(stoken[1].strip())
            if offset< 1: offset = 1
            if offset> len(channels): raise IndexError
            logging.warn(str(stoken[1])+' converted to '+str(offset))
            retdict = {channels[offset-1]:int(assign)}
        else:
            for c in channels:
                retdict[c]=int(assign)
    else:
        retdict = {int(token):int(assign)}
    return retdict

cmnds.add('lightdata-add', handle_lightdata_add, ['SPACE'], threaded=True)
cmnds.add('lightdata-del', handle_lightdata_del, ['SPACE'], threaded=True)
cmnds.add('lightdata-list', handle_list_lightdata, ['SPACE'], threaded=True)

def handle_lightprofile_add(bot, ievent):
    if not ievent.rest: ievent.missing('<profilename> <channel>=<value>,<c2>=<v2>...') ; return
    ldict = {}
    try:
        splitted_input = ievent.rest.split(' ',1)
        profile = splitted_input[0]
    except:
        ievent.reply('Incorrect Format.');return
    try:
        tdict = token_parse(splitted_input[1])
    except:
        ievent.reply('Parse error.') ; return
    try:
        for token in tdict:
            if int(tdict[token])<0:
                ievent.reply('You must assign appropriate values to channels.') ; return
            else:
                ldict.update(lightdata_lookup(token, tdict[token]))
    except:
        ievent.reply('Syntax error.') ; return

    ievent.reply('Saving: '+profile+': '+str(ldict))
    light_profiles.data[profile.lower()] = ldict
    light_profiles.save()

def handle_lightprofile_save(bot, ievent):
    if not ievent.rest: ievent.missing('<profile name>') ; return
    profile = ievent.rest.split()[0]
    ldict = {i:0 for i in range(1,512)}
    values = chan_multiinfo(ldict)
    ievent.reply('Saving: '+profile+': '+str(ldict))
    light_profiles.data[profile.lower()] = values
    light_profiles.save()

def handle_lightprofile_del(bot, ievent):
    if not ievent.rest: ievent.missing('<profile name>') ; return
    profile = ievent.rest.split()[0]
    try:
        del light_profiles.data[profile]
        light_profiles.save()
    except: ievent.reply("no such profile") ; return
    ievent.reply(profile + " removed")

def handle_list_lightprofiles(bot, ievent):
    """ Show the list of profile names."""
    ievent.reply(str(light_profiles.data.keys()))

def handle_show_lightprofile(bot, ievent):
    """ Show the assignment of a profile."""
    if not ievent.rest: ievent.missing('<profile name>') ; return
    profile = ievent.rest.split()[0]
    try:
        pdata = light_profiles.data[profile]
    except: ievent.reply("no such profile") ; return
    ievent.reply(str(pdata))

def lightprofile_activate(profile, amount=100):
    global light_profiles
    pdata = light_profiles.data[profile]    
    ldata = chan_multiinfo({q:0 for q in range(1,512)})
    ldict = {}
    for x,y in pdata.items():
        if x in ldata.keys():
            y = int(y*amount/100+ldata[x]*(100-amount)/100)
        ldict[x]=y
#    values = chan_multiset(ldict)
    crossfade(ldict, 3)
    return

def handle_lightprofile_activate(bot, ievent):
    """ Activate a profile."""
    if not ievent.rest: ievent.missing('<profile name> (<amount>)') ; return
    splitted = ievent.rest.split()
    profile = splitted[0]
    try:
        amount = float(splitted[1])
        if amount >100: amount = 100
        if amount <0: amount = 0
    except:
        amount = 100
    if profile not in light_profiles.data.keys():
        ievent.reply(profile+' not recognised!') ;return
    lightprofile_activate(profile.lower(), amount)
    if amount <100:
        ievent.reply('Activated profile: '+profile+ ' at '+amount+'%')
    else:
        ievent.reply('Activated profile: '+profile)

cmnds.add('lightprofile-add', handle_lightprofile_add, ['SPACE'], threaded=True)
cmnds.add('lightprofile-save', handle_lightprofile_save, ['SPACE'], threaded=True)
cmnds.add('lightprofile-del', handle_lightprofile_del, ['SPACE'], threaded=True)
cmnds.add('lightprofile-list', handle_list_lightprofiles, ['SPACE'], threaded=True)
cmnds.add('lightprofile-show', handle_show_lightprofile, ['SPACE'], threaded=True)
cmnds.add('lightprofile', handle_lightprofile_activate, ['SPACE'], threaded=True)


def handle_fluoro(bot, ievent):
    """  """
    try:
        splitted_input = ievent.rest.split()
        if splitted_input[0] == '': raise
    except:
        c, l, vlist = chan_info(FLUORO['channel'],FLUORO['channels'])
        clist = range(FLUORO['channel'], FLUORO['channel']+FLUORO['channels'])
        ievent.reply('Current Fluorescent Settings: '+str(zip(clist,vlist)))
        return
    try:
        channelno = int(splitted_input[0])
        if channelno<1 or channelno>FLUORO['channels']: raise
    except: 
        ievent.reply("Invalid entry.") ; return
    c, l, value = chan_toggle(channelno+FLUORO['channel']-1)
    ievent.reply("Toggling " + str(c)+" to "+str(value))

def handle_multichanset(bot, ievent):
    """ Set or view multiple DMX channels. """
    if not ievent.rest: ievent.missing('<channel>=<value>,<c2>=<v2>,...') ; return
    ldict = {}
    lookupdict = {}
    try:
        tdict = token_parse(ievent.rest)
    except:
        ievent.reply('Parse error.') ; return
    try:
        for token in tdict:
            if int(tdict[token])<0:
                lookupdict.update(lightdata_lookup(token, 0))
            else:
                ldict.update(lightdata_lookup(token, tdict[token]))
    except:
        ievent.reply('Syntax error.') ; return
    if len(ldict)>0:
        values = chan_multiset(ldict)
        ievent.reply("Setting " + str(values))
    if len(lookupdict)>0:
        lval = chan_multiinfo(lookupdict)
        ievent.reply(str(lval))

def handle_flash(bot, ievent):
    ievent.reply("Flash executing.")
    flash()

cmnds.add('fluoro', handle_fluoro, ['SPACE'], threaded=True)
examples.add('fluoro', 'Toggles the fluorescent lamps', 'fluoro 1')
cmnds.add('light', handle_multichanset, ['SPACE'], threaded=True)
examples.add('light', 'Used for setting a channel', 'light 1=255')
cmnds.add('flash', handle_flash, ['SPACE','USER'], threaded=True)
examples.add('flash', 'Flashing the lights', 'light')
