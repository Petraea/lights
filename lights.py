# jsb/plugs/myplugs/socket/lights.py
#
# Author: Petraea
#

from jsb.lib.commands import cmnds
from jsb.lib.examples import examples
from jsb.lib.persist import PlugPersist

#from doorsense import currentstatus #<-- Causing some bleedover?

import select, sys, os, time, string
import socket, logging
import json, random

light_config = PlugPersist('light_config')
light_data = PlugPersist('light_data')
light_aliases = PlugPersist('light_aliases')
light_profiles = PlugPersist('light_profiles')

#Custom error for parser
class ParseError(Exception):
    pass

def connectToLB(s=None):
    '''Handler for connecting to the lanbox middleware.'''
    if s is None:
        s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        s.connect((light_config.data['host'],light_config.data['port']))
    return s

def executeLB(command,s=None):
    '''Performs JSON encoding of command lists.'''
    closeafter = False
    if s is None:
        closeafter=True
        s = connectToLB()
    id = random.randint(0,65535)
    command['id']=id
    if 'jsonrpc' not in command:
       command['jsonrpc']='2.0'
    cmd = json.dumps(command)+'\n'
    logging.warn(cmd)
    s.sendall(cmd)
    try:
        ret = json.loads(s.recv(16384))
        assert ret['id'] == id
    except ValueError:
        ret = ''
    logging.warn(ret)
    if closeafter:
        s.close()
    if 'error' in ret:
        if ret['error'] !='':
            raise ValueError(str(ret['error']))
    try:
        return ret['result']
    except:
        return ret

def token_parse(input, separator=',',equator='='):
    '''parses a string with multiple tokens assigned to values e.g. a=3,b,c=4
    into {'a':'3','b':'4','c':'4'}. with ',' as the token separator and '=' as the token equator.
    Only one equator can be used for many tokens i.e this is a many to one parser.
    If it sees any unassigned tokens, it assignes them the special value '-9999' to indicate this.'''
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

def lightdata_lookup(token,assign,separator='-'):
    '''Looks up the token value from the light_data persistent data source.
    Each token can represent a collection of channels not necessarily next to each other.
    It will try to look up integer tokens, otherwise it'll assume it's just a channel number
    Also, splits based on separator (default '-') into subsequent channels in assigned order.'''
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

def crossfade(todict, time = 0.5, layer = 1):
    '''Sets up a crossfade between current light values and the recieved dictionary.'''
    #get the current light values
    fromdict = executeLB({'method':'getChannels','params':[todict]})
    logging.warn(fromdict)
    logging.warn(todict)
    cuelist = 2
    #build a new cue.
    step1={'name':'showscene','fadetype':'crossfade','fadetime':time,'holdtime':0}
    step2={'name':'showscene','fadetype':'crossfade','fadetime':time,'holdtime':float('inf')}
    executeLB({'method':'cueListWrite','params':[cuelist,step1,step2]})
    #transmit the cue steps
    executeLB({'method':'cueSceneWrite','params':[cuelist,1,fromdict]})
    executeLB({'method':'cueSceneWrite','params':[cuelist,2,todict]})
    #execute the cue
    executeLB({'method':'layerGo','params':[cuelist]})

def flash():
    '''Turns off the lights and calls a special flash protocol to attract attention.'''
    fromdict = executeLB({'method':'getChannels'})
    flashon = {u'7':0,u'6':0,u'5':144}
    flashoff = {u'7':0,u'6':0,u'5':0}
    off = {x:0 for x in fromdict.keys()}
    logging.warn('all off')
    executeLB({'method':'setChannels','params':[off]})
    time.sleep(0.5)
    executeLB({'method':'setChannels','params':[flashon]})
    time.sleep(0.3)
    executeLB({'method':'setChannels','params':[flashoff]})
    time.sleep(0.3)
    executeLB({'method':'setChannels','params':[flashon]})
    time.sleep(0.3)
    executeLB({'method':'setChannels','params':[flashoff]})
    time.sleep(0.3)
    executeLB({'method':'setChannels','params':[fromdict]})

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
    values = executeLB({'method':'getChannels'})#Save everything
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
    '''Activates a profile.'''
    logging.warn('Activating profile: %s'%profile)
    global light_profiles
    pdata = light_profiles.data[profile]
    if amount <100:
        ldata = executeLB({'method':'getChannels'})
    else:
        ldata = pdata
    ldict = {}
    for x,y in pdata.items():
        if x in ldata.keys():
            y = int(y*amount/100+ldata[x]*(100-amount)/100)
        ldict[str(x)]=y
    crossfade(ldict, 3)
    return

def handle_lightprofile_activate(bot, ievent):
    """ Handles activating a profile."""
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
        ievent.reply('Activated profile: '+profile+ ' at '+str(amount)+'%')
    else:
        ievent.reply('Activated profile: '+profile)

cmnds.add('lightprofile-add', handle_lightprofile_add, ['SPACE'], threaded=True)
cmnds.add('lightprofile-save', handle_lightprofile_save, ['SPACE'], threaded=True)
cmnds.add('lightprofile-del', handle_lightprofile_del, ['SPACE'], threaded=True)
cmnds.add('lightprofile-list', handle_list_lightprofiles, ['SPACE'], threaded=True)
cmnds.add('lightprofile-show', handle_show_lightprofile, ['SPACE'], threaded=True)
cmnds.add('lightprofile', handle_lightprofile_activate, ['SPACE'], threaded=True)

#TODO
FLUORO={'channel':8,'channels':4}
def handle_fluoro(bot, ievent):
    """  """
    try:
        splitted_input = ievent.rest.split()
        if splitted_input[0] == '': raise ValueError
    except:
        #look up values
        ldict = executeLB({'method':'getChannels','params':[range(FLUORO['channel'],FLUORO['channel']+FLUORO['channels'])]})
        ievent.reply('Current Fluorescent Settings: '+str(ldict))
        return
    try:
        c = int(splitted_input[0])+FLUORO['channel']-1
        if c<FLUORO['channel'] or c>=(FLUORO['channel']+FLUORO['channels']): raise ValueError
    except: 
        ievent.reply("Invalid entry.") ; return
    ldict = executeLB({'method':'toggleChannel','params':[c]})
    ievent.reply("Toggling " + str(c)+" to "+str(ldict))

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
        values = executeLB({'method':'setChannels','params':[ldict]})
        ievent.reply("Setting " + str(values))
    if len(lookupdict)>0:
        lval = executeLB({'method':'getChannels','params':[lookupdict]})
        ievent.reply(str(lval))

def handle_flash(bot, ievent):
#    if currentstatus.data:
    ievent.reply("Flash executing.")
    flash()
#    else:
#        ievent.reply("Space is currently closed.")


cmnds.add('fluoro', handle_fluoro, ['SPACE'], threaded=True)
examples.add('fluoro', 'Toggles the fluorescent lamps', 'fluoro 1')
cmnds.add('light', handle_multichanset, ['SPACE'], threaded=True)
examples.add('light', 'Used for setting a channel', 'light 1=255')
cmnds.add('flash', handle_flash, ['SPACE','USER'], threaded=True)
examples.add('flash', 'Flashing the lights', 'light')
