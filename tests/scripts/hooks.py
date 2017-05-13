set_name('hook_test')

def tick(**kwargs):
    pass

def my_cb(**kwargs):
    pass

attach_man_hook('modman.tick', tick)
attach_custom_hook('mod_one.hook', my_cb)
