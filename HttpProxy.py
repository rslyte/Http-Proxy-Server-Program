#Ryan Slyter
#CS 455 - Programming Assignment 2

from socket import *
from threading import *
from thread import *
import sys
import select
#Entry class to couple data with the date it was last updated
class Entry(object):
        def __init__(self):
		self.etag = ''
                self.date = ''
                self.data = None

#This is a custom class I made to consolidate the 2 critical pieces of data that will be shared by all client_handlers: the dictionary and its lock. Client handlers will need to gain access to the lock
class Dictionary(object):
	def __init__(self):
		self.table = {} #instantiate an empty python dictionary instance
		self.count = 0 #number of items will be 100 before clear called
	def get_data(self, file_name):
		try:
			result = self.table[file_name]
			return result						
		except:
			return None #return nothing if no value for key

	def insert_data(self,file_name, item):
		self.table[file_name] = item
		self.count += 1
		if (self.count >= 64):
			self.clear_data()
		return
	def clear_data(self):
		length = len(self.table.items())/2 #remove half the items in the tree
		for key, item in self.table.items():
			del self.table[key]
			length -= 1
			if length == 0:
				return

def read_all(read_sock):
	predata = ''
	while 1:
		try:
			read, write, error = select.select([read_sock],[],[],0.8)	
			if (read):
				file_request = read_sock.recv(1080)
				if (file_request):
					predata += file_request
				else:
					break	
				#print file_request + '\n'					
			else:
				break
		except:
			'READ_ALL EXCEPTION CAUGHT\n'
			read_sock.close()
			return
	return predata
#ALSO USED FOR DEBUGGING
def detect_content(split_data):
	for line in split_data:
		if ('Transfer-Encoding' in line) or ('Content-Length' in line):
			return True
	return False

global_lock = Lock() #GLOBAL lock we'll need
shared_dict = Dictionary() #GLOBAL dictionary we'll need

#Helper function which is critical to the program
#Goes through a packet and sniffs out the Conneciton
#message, and replaces it with a close indicator to
#the client.
def modify_packet(data_object):
	result = ''
	parsed_o = data_object.split('\r\n')
	count = 0 #used to find the last index
	last_i = len(parsed_o)-1
	cont = detect_content(parsed_o)
	if cont == True: #we know message has a body
		for line in parsed_o: 
			if count == last_i:
				result += '\r\n'
				result += parsed_o[last_i]
				return result
			if 'Connection:' or 'Proxy-Connection:' in line:
				result += 'Connection: close\r\n'
				continue
			result += line
			result += '\r\n'
		return result
	else: #we know message doesn't have a body
		i = 0
		for line in parsed_o:
			#print 'FUCKING LINE IS: ' + line + '\n'
			if 'Connection:' in line:
				print 'found connection close line'
				parsed_o[i] = 'Connection: close'
			i += 1			
		result = '\r\n'.join(parsed_o)
		result += '\r\n\r\n'
		return result

#Custom print function used for debugg.
#Prints an entire packet exception the body	
def print_packet(data_object):
	parsed_o = data_object.split('\r\n')
	size = 0
	for i in parsed_o:
		size+=1
		if size == (len(parsed_o)-1):
			print i + '\n'
			return
		print i + '\n'

#Routine For taking a server response, find an last-mod dat, etag
#or both and adds them to an entry instance that will hold the entire
#modified response
def make_entry(data):
	assert(data != None)
	new_entry = Entry()
	parsed = data.split('\r\n')
	for line in parsed:
	
		if 'Last-Modified' in line:
			date_msg = line[15:] #Just get the date/time info from the line
			print 'modified_msg found was: ' + date_msg
			new_entry.date = date_msg			

		if 'Etag:' in line:
			date_msg = line[6:]
			print 'Etag found was: ' + date_msg
			new_entry.etag = date_msg

	new_entry.data = data #want to just hold the entire message now
	return new_entry
	

#Main subroutine of the script which will represent the various instances of the client_handler threads. ARGS: Client will be used to send data/response back to the client, host will be the url to connect to (with port 80), file_path is the path to the requested file, and dict_lock is the Dictionary class instance to the lock/data.
def client_handler(client, address):

	connection_msg = 'Connection: close\r\n'
	accept_msg = 'HTTP/1.1 200 OK\r\n'
        content_hdr = 'Content-Type:text/html\r\n'

        # Initial Message Parsing of Client Request
	print 'address of client_socket is: ' + str(address) + '\n'
	try:
		predata = read_all(client)
	except BaseException as e:
		print 'EXCEPTION CAUGHT WITH READING FROM CLIENT SOCKET\n'
		print str(e) + '\n'
		client.close()
		return			
	if (predata == None):
		print 'CLIENT SENT NOTHING IT APPEARS'
		client.close()
		return

	final_packet = modify_packet(predata)

	parsed_data = predata.split()
	#if not(parsed_data):
	#	'parsed data was null from split of initial client request\n'
	#	client.close()
	#	return

	#if 'POST' in parsed_data[0]:
	#	print 'FOUND POST REQUEST, EXITING.\n'
	#	client.close()
	#	return
	print '******************************CLIENT SENDS\n\n'
	print_packet(predata)
	target_file = parsed_data[1]
	target_host = parsed_data[4]
		
	print 'target file: ' + str(target_file) + '\n'
	print 'target host: ' + str(target_host) + '\n'

	#Acquire lock object and look up the entry for that full filepath
	global_lock.acquire()
	lookup = shared_dict.get_data(target_file)
	global_lock.release()
	
	get_msg = 'GET ' + target_file + ' HTTP/1.1\r\n'
	host_msg = 'Host: ' + target_host + '\r\n'

	#Connect to the Web Host
	try:
		server_socket = socket(AF_INET, SOCK_STREAM)
		server_socket.connect((target_host,80))
	except BaseException as e:
                print 'Error connecting to Web Host.\n'
		print str(e) + '\n'
		client.close()
                return

	print 'made it past connect.' + '\n'
	#CASE 1: File is not in the Dictionary	
	if (lookup == None):
		print 'made it into lookup == None' + '\n'
		
		server_socket.sendall(final_packet) #just send what the client sent
		
		print 'Made it past all the sending..\n'
		try:
			data = read_all(server_socket)
		except BaseException as e:
			print 'EXCEPTION READING FROM SERVER FROM CASE 1\n'
			print str(e) + '\n'
			client.close()
			return

		print 'Made it past reading in all the data'
		server_socket.close()

		if data == None:
			print 'Server didnt respond.\n'
			client.close()
			return
		parsed_data = data.split('\r\n')
		line = parsed_data[0]
		if ('400' in line) or ('404' in line) or ('505' in line) or ('403' in line):
			client.sendall(data)
			server_socket.close()
			client.close()
			return

		final_packet = modify_packet(data)
		print 'RESPONSE FROM SERVER (NO CACHE HIT) IS: \n'
		print_packet(final_packet)

		if ('200' and 'OK' in final_packet):
			entry = make_entry(final_packet)
			global_lock.acquire()
			shared_dict.insert_data(target_file, entry)
			global_lock.release()
		else:
			print 'THIS NOT A 200 OK PACKET TO STORE: \n'
			print_packet(final_packet)
			print '^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n'
					
		print 'right before sending data back to client\n'
		
		try:
			client.sendall(final_packet)
		except BaseException as e:
			print 'client exception: ' + str(e) + '\r\n'
		
		print 'send must have been successful\n'
		server_socket.close()
		client.close()
		print 'About ready to leave the thread\n'		
		return

	#CASE 2: File is in the Dictionary, but might be outdated
	else:
		print 'made it into the else: part, so lookup != null'
		assert(isinstance(lookup, Entry))#DEBUG
		assert((len(lookup.date) != 0) or (len(lookup.etag) != 0))#DEBUG

		if len(lookup.date) != 0:
			date_msg = 'If-modified-since: ' + lookup.date + '\r\n'
			msg = get_msg + host_msg + date_msg + connection_msg + '\r\n'
			server_socket.sendall(msg)
		else:
			etag_msg = 'If-None-Match: ' + lookup.etag + '\r\n'	
			msg = get_msg + host_msg + etag_msg + connection_msg + '\r\n'
			server_socket.sendall(msg)
		try:
			server_data = read_all(client)
		except BaseException as e:
			print 'EXCEPTION READING FROM THE SERVER.\n'
			print str(e) + '\n'
			return
		print '$$$$$$$$$$$$$$$$$$$$$$$$$$ REPONSE FROM SERVER AFTER AN IF-MOD-SINCE REQUEST: \n'
		print_packet(server_data)
	
		parsed_sdata = server_data.split('\r\n')
		line = parsed_sdata[0]			
		if '304' in line:
			#File is not outdated
			print 'PROOF WE HAVE A CACHE HIT\n'
			assert(lookup.data)	
			client.sendall(lookup.data)
			server_socket.close()
			client.close()
			return

		if ('400' or '404' or '403' or '505' or '301' or '302' in line):
			server_e = modify_packet(server_data)
			client.sendall(server_e)
			client.close()
			server_socket.close()
			return

		
		#final case: file was outdated so new version was sent
		#CRITICAL: I'm assuming that the server sent the modified content resp
		#CASE 3: Get the new modified content, cache it and send back to client
		entry = make_entry(server_data)
		global_lock.acquire()
		shared_dict.insert_data(target_file, entry)
		global_lock.release()
		new_data = modify_packet(server_data)
		print 'newly modified packet is: \n\r'
		print_packet(new_data)
		
		client.sendall(new_data)
		server_socket.close()
		client.close()
		lookup = None #free the old data
		return
		
#****************MAIN PART OF THE SCRIPT***********************#
# Creating the Server proxy socket and passing off accepted    #
# connections to client_handler threads.                       #
if len(sys.argv) <= 1:
	print 'Usage: python HttpProxy.py server_port \n'
	sys.exit(2)

server_port = sys.argv[1]
try:
	port = int(server_port)
except:
	print 'Port number given is not an int. Porgram exit.\n'
	sys.exit(1)

print 'server_port is: ' + str(port) + '\n'
proxy_socket = socket(AF_INET, SOCK_STREAM)
	
try:
	proxy_socket.bind(("localhost",port))
	proxy_socket.listen(5)

except BaseException as e:
	print 'Error creating proxy server.\n'
        print str(e) + '\n'
	sys.exit(1)
 
#Main logic for the server, keep accepting connections and running
#client-handler threads with the Dictionary instance.
threads = [5]
index = 0
while 1:
	if index == 5:
		for i in range(1,4):
			threads[i].join()
		index = 0
	
	client_socket, addr = proxy_socket.accept()			
	try:
		t = Thread(target=client_handler, args=(client_socket, addr))		
		t.start()
		threads.append(t)		
		index += 1
	
	except BaseException as e:
		print 'start new thread went wrong\n'
		print str(e) + '\n'
		break











