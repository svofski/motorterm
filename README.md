# motorterm

This is a simple serial terminal with data plotting capabilities. For tuning my BLDC servo I needed something
that would plot position vs time, preferrably in realtime, to make it easier to analyze and tune different control
loop algorithms and parameters. Thus motorterm was born.

It's built for specific purpose so at the time the customizability is fairly low. The code is simple though,
so it can be modified for other similar purposes without too much effort. In my use case, the interaction 
with the board is done over a serial link. Usually a command sent to the board is a single character 
and the feedback follows a
rudimentary protocol which outputs time, position and velocity. Lines that cannot be parsed into acceptable
data are simply ignored so data to be plotted can be mixed together with extra debug info. The data are read
line by line, parsed, processed and plotted as they come. There are minimal interactive features that 
show exact values at cursor, zero crossing positions, distance from cursor to setpoint. 
There's also a scrollback buffer that allows for examination of text output.

# Requirements

motorterm is written in python 2.7 using pyserial and pygame. There are no other dependencies. Refer to
your system documentation for information about setting up the environment. If you're on Linux and do
some kind of development, chances
are that you already have everything set up. On OSX I use Darwin ports, though other homebrew variants 
also exist.

# Example usage

To debug on a typical USB to serial adapter on OSX at 230400 baud:
```
./graph.py /dev/tty.SLAB_USBtoUART 230400
```

To try a sample test dataset without connection:
```
./graph.py screenlog.0
```

Here's an early version demo video:
[motorterm demo](http://www.youtube.com/watch?v=k-M5uJpWTMw&hd=1)
