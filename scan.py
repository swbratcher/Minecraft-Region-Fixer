#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
#   Region Fixer.
#   Fix your region files with a backup copy of your Minecraft world.
#   Copyright (C) 2011  Alejandro Aguilera (Fenixin)
#   https://github.com/Fenixin/Minecraft-Region-Fixer
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import nbt.region as region
import nbt.nbt as nbt
#~ from nbt.region import STATUS_CHUNK_OVERLAPPING, STATUS_CHUNK_MISMATCHED_LENGTHS
        #~ - STATUS_CHUNK_ZERO_LENGTH
        #~ - STATUS_CHUNK_IN_HEADER
        #~ - STATUS_CHUNK_OUT_OF_FILE
        #~ - STATUS_CHUNK_OK
        #~ - STATUS_CHUNK_NOT_CREATED
from os.path import split, join
import progressbar
import multiprocessing
from multiprocessing import queues
import world
import time

import sys
import traceback

try: import simplejson as json
except ImportError: raise
try: from pprint import pprint
except ImportError: import json

#create a uuid to username dictionary...
try:
    with open('whitelist.json') as whitelist:
        PLAYER_DATA = json.load(whitelist)
        whitelist.close()
        # pprint(PLAYER_DATA)
    print "Loaded whitelist.json for usernames..."
except:
    print "\n\nNOTE: If you load a UUID/Username json file named 'whitelist.json' to the region-fixer.py directory an attempt will be name to convert UUIDs to usernames.\n\n"
    pass


class ChildProcessException(Exception):
    """Takes the child process traceback text and prints it as a
    real traceback with asterisks everywhere."""
    def __init__(self, error):
        # Helps to see wich one is the child process traceback
        traceback = error[2]
        print "*"*10
        print "*** Error while scanning:"
        print "*** ", error[0]
        print "*"*10
        print "*** Printing the child's Traceback:"
        print "*** Exception:", traceback[0], traceback[1]
        for tb in traceback[2]:
            print "*"*10
            print "*** File {0}, line {1}, in {2} \n***   {3}".format(*tb)
        print "*"*10

class FractionWidget(progressbar.ProgressBarWidget):
    """ Convenience class to use the progressbar.py """
    def __init__(self, sep=' / '):
        self.sep = sep

    def update(self, pbar):
        return '%2d%s%2d' % (pbar.currval, self.sep, pbar.maxval)

def scan_world(world_obj, options):
    """ Scans a world folder including players, region folders and
        level.dat. While scanning prints status messages. """
    w = world_obj
    # scan the world dir
    print "Scanning directory..."

    if not w.scanned_level.path:
        print "Warning: No \'level.dat\' file found!"

    if w.players:
        print "There are {0} region files and {1} player files in the world directory.".format(\
            w.get_number_regions(), len(w.players))
    else:
        print "There are {0} region files in the world directory.".format(\
            w.get_number_regions())

    # check the level.dat file and the *.dat files in players directory
    print "\n{0:-^60}".format(' Checking level.dat ')

    if not w.scanned_level.path:
        print "[WARNING!] \'level.dat\' doesn't exist!"
    else:
        if w.scanned_level.readable == True:
            print "\'level.dat\' is readable"
        else:
            print "[WARNING!]: \'level.dat\' is corrupted with the following error/s:"
            print "\t {0}".format(w.scanned_level.status_text)

    print "\n{0:-^60}".format(' Checking player files ')
    # TODO multiprocessing!
    # Probably, create a scanner object with a nice buffer of logger for text and logs and debugs
    if not w.players:
        print "Info: No player files to scan."
    else:
        scan_all_players(w)
        all_ok = True
        for name in w.players:
            if w.players[name].readable == False:
                print "[WARNING]: Player file {0} has problems.\n\tError: {1}".format(w.players[name].filename, w.players[name].status_text)
                all_ok = False
        if all_ok:
            # print w.players
            print "All player files are readable."

    # SCAN ALL THE CHUNKS!
    if w.get_number_regions == 0:
        print "No region files to scan!"
    else:
        for r in w.regionsets:
            if r.regions:
                print "\n{0:-^60}".format(' Scanning the {0} '.format(r.get_name()))
                scan_regionset(r, options)
                # try:
                #     print r.name_tag_log
                #     if os.path.exists("name_tags.json"):
                #         f = open( 'name_tags.json', 'r+' )
                #     else:
                #         f = open( 'name_tags.json', 'w' )
                #     f.write(r.name_tag_log)
                #     f.write('\n')
                #     f.close()
                # except:
                #     print "Something went wrong while saving the name tag file!"
    w.scanned = True


def scan_player(scanned_dat_file,player_name):
    """ At the moment only tries to read a .dat player file. It returns
    0 if it's ok and 1 if has some problem """

    s = scanned_dat_file
    try:
        player_dat = nbt.NBTFile(filename = s.path)
        # print player_dat
        # p_name = str("unknown")
        # p_uuid = str(player_name)
        # this_name_tag = "\nUUID: {0} is \"{1}\" and is at {2} {3} {4}.\n".format(p_uuid, p_name, int(float(player_dat["Pos"][0].value)), int(float(player_dat["Pos"][1].value)), int(float(player_dat["Pos"][2].value)))
        # print this_name_tag

        s.readable = True
    except Exception, e:
        s.readable = False
        s.status_text = e


def scan_all_players(world_obj):
    """ Scans all the players using the scan_player function. """

    for name in world_obj.players:
        scan_player(world_obj.players[name],name)


def scan_region_file(scanned_regionfile_obj, options):
    """ Given a scanned region file object with the information of a 
        region files scans it and returns the same obj filled with the
        results.
        
        If delete_entities is True it will delete entities while
        scanning
        
        entiti_limit is the threshold tof entities to conisder a chunk
        with too much entities problems.
    """
    o = options
    delete_entities = o.delete_entities
    entity_limit = o.entity_limit
    name_tag_log = ""
    try:
        r = scanned_regionfile_obj
        # counters of problems
        chunk_count = 0
        corrupted = 0
        wrong = 0
        entities_prob = 0
        shared = 0
        # used to detect chunks sharing headers
        offsets = {}
        filename = r.filename
        # try to open the file and see if we can parse the header
        try:
            region_file = region.RegionFile(r.path)
        except region.NoRegionHeader: # the region has no header
            r.status = world.REGION_TOO_SMALL
            return r
        except IOError, e:
            print "\nWARNING: I can't open the file {0} !\nThe error is \"{1}\".\nTypical causes are file blocked or problems in the file system.\n".format(filename,e)
            r.status = world.REGION_UNREADABLE
            r.scan_time = time.time()
            print "Note: this region file won't be scanned and won't be taken into acount in the summaries"
            # TODO count also this region files
            return r
        except: # whatever else print an error and ignore for the scan
                # not really sure if this is a good solution...
            print "\nWARNING: The region file \'{0}\' had an error and couldn't be parsed as region file!\nError:{1}\n".format(join(split(split(r.path)[0])[1], split(r.path)[1]),sys.exc_info()[0])
            print "Note: this region file won't be scanned and won't be taken into acount."
            print "Also, this may be a bug. Please, report it if you have the time.\n"
            return None

        try:# start the scanning of chunks
            
            for x in range(32):
                for z in range(32):

                    # start the actual chunk scanning
                    g_coords = r.get_global_chunk_coords(x, z)
                    chunk, c = scan_chunk(region_file, (x,z), g_coords, o)
                    if c != None: # chunk not created
                        r.chunks[(x,z)] = c
                        chunk_count += 1
                    else: continue
                    if c[TUPLE_STATUS] == world.CHUNK_OK:
                        if options.name_tags == True:
                            if len(chunk["Level"]["Entities"]) > 0:
                                for idx, val in enumerate(chunk["Level"]["Entities"]):
                                    
                                    # print val["id"]
                                    try:
                                        this_name_tag = ""
                                        this_customname = ""
                                        if 'OwnerUUID' in val:
                                            if str(val["OwnerUUID"]) != "":
                                                # pprint(PLAYER_DATA)
                                                try:
                                                    username = [u["name"] for u in PLAYER_DATA if u["uuid"] == str(val["OwnerUUID"])]
                                                    this_owner = username[0]
                                                except:
                                                    this_owner = str(val["OwnerUUID"])
                                                this_owner += "'s "
                                            else:
                                                this_owner = ""
                                        elif 'Owner' in val:
                                            if str(val["Owner"]) != "":
                                                this_owner = str(val["Owner"])
                                                this_owner += "'s "
                                        else:
                                            this_owner = ""
                                        if 'CustomName' in val:
                                            if str(val["CustomName"]) != "":
                                               this_customname = "\"" + str(val["CustomName"]) + "\""
                                        # determine if a horse
                                        if str(val["id"]) == "EntityHorse":
                                            # print val
                                            if str(val["Tame"]) == "1":
                                                # print "HORSE:"
                                                # print "\ttame"
                                                # this_name_tag += "\n{0}'s horse {2} is at {3} {4} {5} ({4})".format(str(val["OwnerUUID"]), str(val["CustomName"]), int(float(val["Pos"][0].value)), int(float(val["Pos"][1].value)), int(float(val["Pos"][2].value)))
                                                # this_name_tag += "id: {0}".format(str(val["id"]))
                                                jump = speed = health = ""
                                                for at in val["Attributes"]:
                                                    # print at
                                                    if str(at["Name"]) == "horse.jumpStrength":
                                                        jump = "%.3f" % float(at["Base"].value)
                                                    elif str(at["Name"]) == "generic.movementSpeed":
                                                        speed = "%.3f" % float(at["Base"].value)
                                                    elif str(at["Name"]) == "generic.maxHealth":
                                                        health = int(float(at["Base"].value))
                                                # Type: The type of the horse. 0 = Horse, 1 = Donkey, 2 = Mule, 3 = Zombie, 4 = Skeleton.
                                                if this_customname == "":
                                                    if str(val["Type"]) == "0":
                                                       this_customname = "Horse"
                                                    elif str(val["Type"]) == "1":
                                                       this_customname = "Donkey"
                                                    elif str(val["Type"]) == "2":
                                                       this_customname = "Mule"
                                                    elif str(val["Type"]) == "3":
                                                       this_customname = "ZombieHorse"
                                                    elif str(val["Type"]) == "4":
                                                       this_customname = "Skeleton"
                                                this_name_tag += "{5}{0} is at {1} {2} {3} ({4}: J {6} / S {7} / H {8}).".format(this_customname, int(float(val["Pos"][0].value)), int(float(val["Pos"][1].value)), int(float(val["Pos"][2].value)), val["id"], this_owner, jump, speed, health)
                                                print this_name_tag
                                                continue
                                        # determine if a dog
                                        elif str(val["id"]) == "Wolf":
                                            if this_owner != "":
                                                # print "WOLF:"
                                                # print "\ttame"
                                                if this_customname == "":
                                                    this_customname = "wolf"
                                                this_name_tag += "{5}{0} is at {1} {2} {3} ({4}).".format(this_customname, int(float(val["Pos"][0].value)), int(float(val["Pos"][1].value)), int(float(val["Pos"][2].value)), val["id"], this_owner)
                                                print this_name_tag
                                                continue
                                        # determine if a cat
                                        elif str(val["id"]) == "Ozelot":
                                            # print val
                                            if 'Tame' in val:
                                                if str(val["Tame"]) == "1":
                                                    # print "CAT:"
                                                    if this_customname == "":
                                                        this_customname = "cat"
                                                    this_name_tag += "{5}{0} is at {1} {2} {3} ({4}).".format(this_customname, int(float(val["Pos"][0].value)), int(float(val["Pos"][1].value)), int(float(val["Pos"][2].value)), val["id"], this_owner)
                                                    print this_name_tag
                                                continue
                                        # catch if random creature that's named
                                        try:
                                            if str(val["CustomName"]) != "":
                                                # print "CUSTOMNAME:"
                                                # TODO Don't simply print this. Store it to display as part of a summary that doesn't interrupt the progress bar.
                                                this_name_tag += "The {4}, {0} is at {1} {2} {3}.".format(this_customname, int(float(val["Pos"][0].value)), int(float(val["Pos"][1].value)), int(float(val["Pos"][2].value)), val["id"])
                                                print this_name_tag
                                            continue
                                        except:
                                            pass
                                    except:
                                        print "Unexpected error:", sys.exc_info()[0]
                                        raise      
                        continue
                    elif c[TUPLE_STATUS] == world.CHUNK_TOO_MANY_ENTITIES:
                        # deleting entities is in here because parsing a chunk with thousands of wrong entities
                        # takes a long time, and once detected is better to fix it at once.
                        if delete_entities:
                            world.delete_entities(region_file, x, z)
                            print "Deleted {0} entities in chunk ({1},{2}) of the region file: {3}".format(c[TUPLE_NUM_ENTITIES], x, z, r.filename)
                            # entities removed, change chunk status to OK
                            r.chunks[(x,z)] = (0, world.CHUNK_OK)

                        else:
                            entities_prob += 1
                            # This stores all the entities in a file,
                            # comes handy sometimes.
                            #~ pretty_tree = chunk['Level']['Entities'].pretty_tree()
                            #~ name = "{2}.chunk.{0}.{1}.txt".format(x,z,split(region_file.filename)[1])
                            #~ archivo = open(name,'w')
                            #~ archivo.write(pretty_tree)

                    elif c[TUPLE_STATUS] == world.CHUNK_CORRUPTED:
                        corrupted += 1
                    elif c[TUPLE_STATUS] == world.CHUNK_WRONG_LOCATED:
                        wrong += 1
            
            # Now check for chunks sharing offsets:
            # Please note! region.py will mark both overlapping chunks
            # as bad (the one stepping outside his territory and the
            # good one). Only wrong located chunk with a overlapping
            # flag are really BAD chunks! Use this criterion to 
            # discriminate
            metadata = region_file.metadata
            sharing = [k for k in metadata if (
                metadata[k].status == region.STATUS_CHUNK_OVERLAPPING and
                r[k][TUPLE_STATUS] == world.CHUNK_WRONG_LOCATED)]
            shared_counter = 0
            for k in sharing:
                r[k] = (r[k][TUPLE_NUM_ENTITIES], world.CHUNK_SHARED_OFFSET)
                shared_counter += 1

        except KeyboardInterrupt:
            print "\nInterrupted by user\n"
            # TODO this should't exit
            sys.exit(1)

        r.chunk_count = chunk_count
        r.corrupted_chunks = corrupted
        r.wrong_located_chunks = wrong
        r.entities_prob = entities_prob
        r.shared_offset = shared_counter
        r.scan_time = time.time()
        r.status = world.REGION_OK
        r.name_tag_log = name_tag_log
        
        return r 

        # Fatal exceptions:
    except:
        # anything else is a ChildProcessException
        except_type, except_class, tb = sys.exc_info()
        r = (r.path, r.coords, (except_type, except_class, traceback.extract_tb(tb)))
        return r

def multithread_scan_regionfile(region_file):
    """ Does the multithread stuff for scan_region_file """
    r = region_file
    o = multithread_scan_regionfile.options

    # call the normal scan_region_file with this parameters
    r = scan_region_file(r,o)

    # exceptions will be handled in scan_region_file which is in the
    # single thread land
    multithread_scan_regionfile.q.put(r)



def scan_chunk(region_file, coords, global_coords, options):
    """ Takes a RegionFile obj and the local coordinatesof the chunk as
        inputs, then scans the chunk and returns all the data."""
    try:
        chunk = region_file.get_chunk(*coords)
        data_coords = world.get_chunk_data_coords(chunk)
        num_entities = len(chunk["Level"]["Entities"])
        if data_coords != global_coords:
            status = world.CHUNK_WRONG_LOCATED
            status_text = "Mismatched coordinates (wrong located chunk)."
            scan_time = time.time()
        elif num_entities > options.entity_limit:
            status = world.CHUNK_TOO_MANY_ENTITIES
            status_text = "The chunks has too many entities (it has {0}, and it's more than the limit {1})".format(num_entities, options.entity_limit)
            scan_time = time.time()
        else:
            status = world.CHUNK_OK
            status_text = "OK"
            scan_time = time.time()

    except region.InconceivedChunk as e:
        chunk = None
        data_coords = None
        num_entities = None
        status = world.CHUNK_NOT_CREATED
        status_text = "The chunk doesn't exist"
        scan_time = time.time()

    except region.RegionHeaderError as e:
        error = "Region header error: " + e.msg
        status = world.CHUNK_CORRUPTED
        status_text = error
        scan_time = time.time()
        chunk = None
        data_coords = None
        global_coords = world.get_global_chunk_coords(split(region_file.filename)[1], coords[0], coords[1])
        num_entities = None

    except region.ChunkDataError as e:
        error = "Chunk data error: " + e.msg
        status = world.CHUNK_CORRUPTED
        status_text = error
        scan_time = time.time()
        chunk = None
        data_coords = None
        global_coords = world.get_global_chunk_coords(split(region_file.filename)[1], coords[0], coords[1])
        num_entities = None

    except region.ChunkHeaderError as e:
        error = "Chunk herader error: " + e.msg
        status = world.CHUNK_CORRUPTED
        status_text = error
        scan_time = time.time()
        chunk = None
        data_coords = None
        global_coords = world.get_global_chunk_coords(split(region_file.filename)[1], coords[0], coords[1])
        num_entities = None

    return chunk, (num_entities, status) if status != world.CHUNK_NOT_CREATED else None

#~ TUPLE_COORDS = 0
#~ TUPLE_DATA_COORDS = 0
#~ TUPLE_GLOBAL_COORDS = 2
TUPLE_NUM_ENTITIES = 0
TUPLE_STATUS = 1

#~ def scan_and_fill_chunk(region_file, scanned_chunk_obj, options):
    #~ """ Takes a RegionFile obj and a ScannedChunk obj as inputs,
        #~ scans the chunk, fills the ScannedChunk obj and returns the chunk
        #~ as a NBT object."""
#~
    #~ c = scanned_chunk_obj
    #~ chunk, region_file, c.h_coords, c.d_coords, c.g_coords, c.num_entities, c.status, c.status_text, c.scan_time, c.region_path = scan_chunk(region_file, c.h_coords, options)
    #~ return chunk

def _mp_pool_init(regionset,options,q):
    """ Function to initialize the multiprocessing in scan_regionset.
    Is used to pass values to the child process. """
    multithread_scan_regionfile.regionset = regionset
    multithread_scan_regionfile.q = q
    multithread_scan_regionfile.options = options


def scan_regionset(regionset, options):
    """ This function scans all te region files in a regionset object
    and fills the ScannedRegionFile obj with the results
    """

    total_regions = len(regionset.regions)
    total_chunks = 0
    corrupted_total = 0
    wrong_total = 0
    entities_total = 0
    too_small_total = 0
    unreadable = 0

    # init progress bar
    if not options.verbose:
        pbar = progressbar.ProgressBar(
            widgets=['Scanning: ', FractionWidget(), ' ', progressbar.Percentage(), ' ', progressbar.Bar(left='[',right=']'), ' ', progressbar.ETA()],
            maxval=total_regions)

    # queue used by processes to pass finished stuff
    q = queues.SimpleQueue()
    pool = multiprocessing.Pool(processes=options.processes,
            initializer=_mp_pool_init,initargs=(regionset,options,q))

    if not options.verbose:
        pbar.start()

    # start the pool
    # Note to self: every child process has his own memory space,
    # that means every obj recived by them will be a copy of the
    # main obj
    result = pool.map_async(multithread_scan_regionfile, regionset.list_regions(None), max(1,total_regions//options.processes))

    # printing status
    region_counter = 0

    while not result.ready() or not q.empty():
        time.sleep(0.01)
        if not q.empty():
            r = q.get()
            if r == None: # something went wrong scanning this region file
                          # probably a bug... don't know if it's a good
                          # idea to skip it
                continue
            if not isinstance(r,world.ScannedRegionFile):
                raise ChildProcessException(r)
            else:
                corrupted, wrong, entities_prob, shared_offset, num_chunks = r.get_counters()
                filename = r.filename
                # the obj returned is a copy, overwrite it in regionset
                regionset[r.get_coords()] = r
                corrupted_total += corrupted
                wrong_total += wrong
                total_chunks += num_chunks
                entities_total += entities_prob
                if r.status == world.REGION_TOO_SMALL:
                    too_small_total += 1
                elif r.status == world.REGION_UNREADABLE:
                    unreadable += 1
                region_counter += 1
                if options.verbose:
                  if r.status == world.REGION_OK:
                    stats = "(c: {0}, w: {1}, tme: {2}, so: {3}, t: {4})".format( corrupted, wrong, entities_prob, shared_offset, num_chunks)
                  elif r.status == world.REGION_TOO_SMALL:
                    stats = "(Error: not a region file)"
                  elif r.status == world.REGION_UNREADABLE:
                    stats = "(Error: unreadable region file)"
                  print "Scanned {0: <12} {1:.<43} {2}/{3}".format(filename, stats, region_counter, total_regions)
                else:
                    pbar.update(region_counter)

    if not options.verbose: pbar.finish()

    regionset.scanned = True
