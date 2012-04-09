import signal, code, traceback

def signal_handler( signal_number ):
    """
    A decorator to set the specified function as handler for a signal.
    This function is the 'outer' decorator, called with only the (non-function) 
    arguments
    """
    
    # create the 'real' decorator which takes only a function as an argument
    def __decorator( function ):
        signal.signal( signal_number, function )
        return function
    
    return __decorator

@signal_handler(signal.SIGINT)
def debug_handler(sig, frame):
    """Interrupt running process, and provide a python prompt for
    interactive debugging."""
    d={'_frame':frame}         # Allow access to frame object.
    d.update(frame.f_globals)  # Unless shadowed by global
    d.update(frame.f_locals)

    i = code.InteractiveConsole(d)
    message  = "Signal recieved : entering python shell.\nTraceback:\n"
    message += ''.join(traceback.format_stack(frame))
    i.interact(message)
