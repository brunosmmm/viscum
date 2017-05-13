#set name
set_name('ticker')

print("Hello, world!")

def tick(**kwargs):
    print('tick')

#attach to module manager tick
attach_man_hook('modman.tick', tick)

print("Done!")
