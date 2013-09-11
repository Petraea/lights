# jsb/plugs/myplugs/socket/lights.py
#
# Author: Petraea
#

from jsb.lib.commands import cmnds
from jsb.lib.examples import examples
from jsb.lib.persist import PlugPersist

import select, sys, os, time, string
import socket

LIGHTSERVER = ('lanbox.nurdspace.lan', 777)
LIGHTSERVER_PASSWORD='777\n'

light_data = PlugPersist('light_data')
light_aliases = PlugPersist('light_aliases')
light_profiles = PlugPersist('light_profiles')

DESKDIMMER = {'channel':1,'channels':4}
STROBE = {'channel':5,'channels':4}
FLUORO = {'channel':9,'channels':4}
LED1 = {'channel':32,'channels':3}
LED2 = {'channel':35,'channels':3}
LED3 = {'channel':38,'channels':3}
LED4 = {'channel':41,'channels':3}
LED5 = {'channel':44,'channels':3}
LED6 = {'channel':47,'channels':3}


FLUOROALIASES = {'gaming':4,'desks':3,'printers':2,'middle':1}

#Custom error for parser
class ParseError(Exception):
    pass

def split_by_n( seq, n ):
    while seq:
        yield seq[:n]
        seq = seq[n:]

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
    print(n)
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
            print ('sep')
            token = token.strip()
            if token == '': raise ParseError("Tokens can't be blank.")
            if assigning:
                for i in toassign:
                    print ('assign: '+i+':'+token)
                    tdict[i.lower()]=token
                toassign = []
                assigning = False
                token = ''
            else:
                print ('token: '+token)
                toassign.append(token)
                token = ''
        elif c == equator:
            print ('eq')
            token = token.strip()
            if not assigning:
                assigning = True
                toassign.append(token)
                token = ''
            else:
                raise ParseError("Two equals in a row?")
        else:
            print (c)
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
    l = hex(layer)[2:].zfill(2)
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s = connectToLB(s)
    retdict = {}
    for light in lightdict:
        if lightdict[light]<0: lightdict[light] = 0
        if lightdict[light]>255: lightdict[light] = 255
        c = hex(light)[2:].zfill(4)
        v = hex(lightdict[light])[2:].zfill(2)
        executeLB(s,'C9'+l+c+v)
        retdict[light]=lightdict[light]
    s.close()
    return retdict

def chan_multiinfo(lightdict,layer = 1):
    l = hex(layer)[2:].zfill(2)
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s = connectToLB(s)
    retdict = {}
    for light in lightdict:
        c = hex(light)[2:].zfill(4)
        retdict[light] = int(executeLB(s,'CD'+l+c+'01'),16)
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
    executeLB(s,'C9'+layer+'0006'+'40') #Medium rate
    executeLB(s,'C9'+layer+'0005'+'C0') #Flash ON!
    time.sleep(1)
    sendstream = ''
    for i in range(1,len(chanlist)):
        sendstream += hex(i)[2:].zfill(4)
        sendstream += chanlist[i-1].zfill(2)
    executeLB(s,'C9'+layer+sendstream) #Restore
    s.close()

def handle_lightdata_add(bot, ievent):
    if not ievent.rest: ievent.missing('<light name> <start channel> <num channels>') ; return
    try:
        splitted_input = ievent.rest.split()
        lightname = splitted_input[0]
        channel = int(splitted_input[1])
        channels = int(splitted_input[2])
    except:
        ievent.reply('Incorrect Format.')
    ievent.reply('Saving: '+lightname+' channel: '+str(channel)+'('+str(channels)+')')
    light_data.data[lightname.lower()] = (channel, channels)
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
    if stoken[0].strip() in lights:
        channel, channels = lights[stoken[0].strip()]
        if len(stoken)==2:
            offset = int(stoken[1])
            if offset< channels: offset = 1
            if offset> channels: raise IndexError
            retdict = {channel+offset-1:int(assign)}
        else:
            for c in range(channels):
                retdict[channel+c]=int(assign)
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
    pdata = light_profiles.data[profile]    
    ldata = chan_multiinfo({x:0 for x in range(1,512)})
    ldict = {}
    for x,y in pdata.data():
        y = int(y*amount/100+ldata[x]*(100-amount)/100)
        ldict[x]=y
    values = chan_multiset(ldict)
    return values

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
    light_profile_activate(profile.lower(), amount)
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
        try:
           al = splitted_input[0].lower()
           channelno = FLUOROALIASES[al]
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
cmnds.add('flash', handle_flash, ['SPACE'], threaded=True)
examples.add('flash', 'Flashing the lights', 'light')
