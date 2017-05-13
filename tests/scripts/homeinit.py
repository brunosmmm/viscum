#set name
set_name('homeinit')

print("Initializing...")

#load plugins manually
load_module('mpd', address='localhost', port=6600)

print("Done!")
