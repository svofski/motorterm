#!/usr/bin/env python

import pygame
import serial
import re
import threading
import sys
from time import sleep
from math import sqrt

Running = True

Dimension = (1024,768)
SeparatorPosition = Dimension[1] - 80

TIMEREVENT = pygame.USEREVENT + 1
SERIALEVENT = pygame.USEREVENT + 2
BgColor = pygame.Color(0, 0, 0, 255)
FgColor = pygame.Color(255, 255, 255, 255)
PosLineColor = pygame.Color(200, 200, 255, 255)
PosNodeColor = pygame.Color(255, 200, 220, 255)

VelLineColor = pygame.Color(80, 150, 100, 255)
VelNodeColor = pygame.Color(100, 255, 255, 255)

HighlightNodeColor = pygame.Color(255, 255, 255, 255)

PlotTextColor = pygame.Color(255, 255, 255, 255)
TextMarkerBgColor = pygame.Color(0, 0, 100, 255)
TextMarkerColor = pygame.Color(255, 255, 0, 255)
LocalLabelTextColor = pygame.Color(0, 0, 0, 255)
MarkerColor = pygame.Color(255, 100, 100, 128)
MouseColor  = pygame.Color(255, 100, 255, 128)
TextWinBgColor = pygame.Color(0, 0, 22, 255)
TextWinFgColor = pygame.Color(255, 255, 150, 255)

SeparatorColor = pygame.Color(100, 110, 100, 20)
PlotFrameColor = SeparatorColor
ScrollBarColor = SeparatorColor

FontName, FontSize, BigFontSize = 'Andale Mono', 11, 24

Font = None
LineHeight = FontSize + 2
BigFont = None

# Mouse control states for the main loop
DEFULAT = 0
RESIZE = 1

class Buffer:
    last = ''
    buf = [''] * 128
    head = 0
    count = 0
    OnChange = None

    def __init__(self):
        self.count = 0

    def Count(self):
        return min(self.count, len(self.buf))

    def NewLine(self, line):
        self.head = (self.head + 1) % len(self.buf)
        self.buf[self.head] = line
        self.count = self.count + 1
        if self.OnChange != None:
            self.OnChange()

    def Enumerate(self):
        cursor = self.head
        for count in xrange(len(self.buf)):
            yield self.buf[cursor]
            cursor = cursor - 1
            if cursor < 0:
                cursor = len(self.buf) - 1

class Connection(object):
    Open = False
    Enabled = False

    def __init__(self):
        self.Open = True

    def Send(self, key):
        pass

    def ReceiveLine(self):
        pass

    def Close(self):
        self.Open = False

    def Enable(self, value):
        self.Enabled = value

class SerialConnection(Connection):
    cer = None
    pollThread = None

    def __init__(self, device, speed):
        super(SerialConnection, self).__init__()
        self.cer = serial.Serial(device, speed, timeout=1)
        self.pollThread = threading.Thread(target=self.PollThreadFunc, args=[])
        self.pollThread.setDaemon(True)
        self.pollThread.start()

    def Send(self, key):
        try:
            self.cer.write(key.encode('ascii'))
            self.cer.flush()
            return True
        except:
            return False

    def ReceiveLine(self):
        return self.cer.readline() if self.cer.inWaiting() > 0 else None

    def PollThreadFunc(self):
        while self.Open:
            if self.Enabled and (self.cer.inWaiting() > 0):
                pygame.event.post(pygame.event.Event(SERIALEVENT))
            sleep(0.01)

class FileConnection(Connection):
    pollThread = None
    text = None

    def __init__(self, file):
        super(FileConnection, self).__init__()
        self.text = open(file, 'r')
        self.pollThread = threading.Thread(target=self.PollThreadFunc, args=[])
        self.pollThread.setDaemon(True)
        self.pollThread.start()

    def ReceiveLine(self):
        line = self.text.readline()
        if len(line) == 0:
            self.Open = False
            return None
        return line

    def PollThreadFunc(self):
        while self.Open:
            if self.Enabled:
                pygame.event.post(pygame.event.Event(SERIALEVENT))
            sleep(0.01)
   
class DataProtocol:
    samples = [None] * 0
    ranges = [[0,0]] * 3
    crossings = []
    regex = re.compile(r'T=(?P<time>[\-0-9]+) Q=(?P<qenc>[\-0-9]+).*vel=(?P<vel>[\-0-9]+)')
    VelocityMovingAverage = False
    OnChange = None

    def ProcessData(self, line):
        line = line.strip()
        if line == 'STOP':
            self.Finish()
            return
        if line == 'START':
            self.Start()
            return
        m = self.regex.match(line)
        if m != None:
            time = int(m.group('time'))
            qenc = int(m.group('qenc'))
            vel = int(m.group('vel'))

            self.Sample((time, qenc, vel))

    def Start(self):
        self.samples = [None] * 0
        self.ranges = [[100500,-100500], [100500,-100500], [100500,-100500]]
        if self.OnChange != None: self.OnChange()

    def Finish(self):
        pass

    def Sample(self, samp):
        # recalculate velocity into proper bananas
        v = 2000.0/samp[2] if samp[2] != 0 else 2000.0

        if self.VelocityMovingAverage:
            if len(self.samples) > 0:
                v = (self.samples[-1][2] + v) / 2
    
        # store sample: time (/10.0 for milliseconds), encoder value
        s = (samp[0]/10.0, samp[1], v)
        self.samples.append(s)
        for index in [1,2]:
            if s[index] < self.ranges[index][0]:
                self.ranges[index][0] = s[index]
            if s[index] > self.ranges[index][1]:
                self.ranges[index][1] = s[index]

        self.updateZeroCrossings()

        if self.OnChange != None: self.OnChange()

    def updateZeroCrossings(self):
        y = self.samples[-1][1]
        prev = self.samples[0]
        self.crossings = []
        for s in self.samples[1:-1]:            
            if ((prev[1] < y) and (s[1] >= y)) or ((prev[1] >= y) and (s[1] < y)):
                k = (s[1] - prev[1])/(s[0] - prev[0])
                x = (y - prev[1])/k + prev[0]
                self.crossings.append((x,y))
            prev = s


    def chunks(self, l, n):
        for i in xrange(0, len(l), n):
            yield l[i:i+n]

    def decimate(self, data, factor):
        r = []
        for x in self.chunks(data, factor):
            t = x[0][0]
            s = sum([s[2] for s in x])
            r.append((t, 1.0 * s / factor))
        return r

    def Samples(self, index):
        return [(x[0], x[index]) for x in self.samples] # position

    def XSamples(self, index):
        for s in self.samples:
            yield (s[0], s[index])

    def Count(self):
        return len(self.samples)

    def Range(self, index):
        return self.ranges[index]

    # find the nearest sample for specified time
    def SearchTime(self, time):
        first = 0
        last = len(self.samples)-1
        nearest = -1
        neardist = 100500

        while first <= last:
            midpoint = (first + last) // 2
            dist = abs(self.samples[midpoint][0] - time)
            if dist < neardist:
                neardist = dist
                nearest = midpoint

            if time < self.samples[midpoint][0]:
                last = midpoint - 1
            else:
                first = midpoint + 1
        if nearest != -1:
            return nearest, neardist, self.samples[nearest]
        else:
            return -1, -1, None


class Graph:
    surface = None
    plotsurface = None
    rect = None
    dirty = True
    data = None
    scaler = [lambda x: x, lambda x: x, lambda x: x]
    invscaler = [lambda x: x, lambda x: x, lambda x: x]
    mouseX, mouseY = 0, 0
    POI = None
    plotlabels = []

    def __init__(self, dimension, dataprovider):
        self.Resize(dimension)
        self.data = dataprovider
        self.data.OnChange = self.DataChanged

    def DataChanged(self):
        self.POI = None
        self.dirty = True

    def Resize(self, dimension):
        self.rect = pygame.Rect((40, 0), (dimension[0] - 60, dimension[1] - 20))
        self.surface = pygame.Surface(dimension)
        self.plotsurface = self.surface.subsurface(self.rect)
        self.dirty = True

    def searchPOI(self):
        position = self.invscaler[1]((self.mouseX, self.mouseY))
        velocity = self.invscaler[2]((self.mouseX, self.mouseY))
        index, dist, point = self.data.SearchTime(position[0])
        if index != -1:
            dist = lambda x1, y1, x2, y2: sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

            dp = dist(position[0], position[1], point[0], point[1])
            dv = dist(velocity[0], velocity[1], point[0], point[2])

            if (dp <= 6) or (dv <= 6):
                if dv < dp:
                    self.POI = (2, index, point[0], point[2])
                else:
                    self.POI = (1, index, point[0], point[1])
            else:
                self.POI = None

    def MouseMove(self, pos):
        self.mouseX, self.mouseY = pos[0] - self.rect.left, pos[1] - self.rect.top
        self.searchPOI()
        self.dirty = True

    def plot(self, data, yrange, LineColor, NodeColor, plotIndex, crossings=[]):
        ymin, ymax = yrange
        line = pygame.draw.line
        circle = pygame.draw.circle
        rotate = pygame.transform.rotate
        width, height = self.rect.width, self.rect.height

        # create mappings: plot to screen (scaler) and screen to plot (invscaler)
        swing = abs(ymax - ymin)
        xscale, yscale = (1.0 * width / (data[-1][0] - data[0][0]), 
                          1.0 * height / swing if swing > 0.1 else 1)
        
        offset = (data[0][0], ymin + (ymax-ymin)/2)
        self.scaler[plotIndex] = lambda samp: \
            ((samp[0]-offset[0]) * xscale, height/2 - (samp[1]-offset[1]) * yscale)
        self.invscaler[plotIndex] = lambda samp: \
            (samp[0] / xscale + offset[0], ymax - samp[1]/yscale)
        scaler = self.scaler[plotIndex]

        end = scaler(data[-1])

        if plotIndex == 1:            
            # draw middle line (servo setpoint)
            line(self.plotsurface, MarkerColor, (0, end[1]), (width-1, end[1]))

            # Check zero crossing and draw a marker and a label if there is one
            for cross in crossings:
                xy = scaler(cross)
                line(self.plotsurface, MarkerColor, (xy[0], end[1]-5), (xy[0], end[1]+5))
                label = rotate(
                    Font.render('%4.1f' % cross[0], 0, TextMarkerColor, TextMarkerBgColor), 90)
                labely = end[1] + (20 if end[1] < height/2 else - 20 - label.get_height())
                #self.plotsurface.blit(label, (xy[0] - label.get_width()/2, labely))
                self.plotlabels.append((label, (xy[0] - label.get_width()/2, labely)))


            label = Font.render(str(ymin), 0, LineColor)
            self.surface.blit(label, (2, height - label.get_height()))

            label = Font.render(str(ymax), 0, LineColor)
            self.surface.blit(label, (2, 0))

            # draw setpoint label
            label = Font.render(str(data[-1][1]), 0, MarkerColor)
            self.surface.blit(label, (self.rect.right + 2, end[1] - label.get_height()/2))
        
            
            if (self.mouseY >= 0) and (self.mouseY < self.plotsurface.get_height()): 
                # draw horizontal line at mouse cursor    
                line(self.plotsurface, MouseColor, (1, self.mouseY), (width - 1, self.mouseY))
                # draw a label indicating position corresponding to mouse cursor
                value = ymax - self.mouseY / yscale
                label = Font.render('%3.1f' % (value), 0, MouseColor)
                self.surface.blit(label, (2, self.mouseY - label.get_height()/2))
                # draw vertical line that shows distance from mouse position to servo setpoint 
                line(self.surface, MouseColor, 
                    (self.rect.right + 5, self.mouseY), (self.rect.right + 5, end[1]))
                # draw the distance from mouse to setpoint
                label = rotate(Font.render('%d' % (value - data[-1][1]), 0, MouseColor), 90)
                labely = (self.mouseY + end[1]) / 2;
                self.surface.blit(label, (self.rect.right + 8, labely))

        # Draw the actual plot
        xyses = [scaler(xy) for xy in data]
        pygame.draw.lines(self.plotsurface, LineColor, False, xyses, 1)
        for xy in xyses:
            circle(self.plotsurface, NodeColor, [int(round(p)) for p in xy], 2, 1)

        if (self.POI != None) and (self.POI[0] == plotIndex):
            index = self.POI[1]
            point = scaler(data[index])
            circle(self.plotsurface, HighlightNodeColor, [int(round(x)) for x in point], 4, 0)
            label = Font.render('%4.1f, %4.1f' % (data[index][0], data[index][1]), 0, LocalLabelTextColor, LineColor)

            labelpos = [point[0] + 4, point[1] - label.get_height() - 4]
            if labelpos[0] + label.get_width() >= self.rect.right:
                labelpos[0] = point[0] - label.get_width() - 4
            if labelpos[1] <= 0:
                labelpos[1] = point[1] + 4
            self.plotlabels.append((label, labelpos))

        return end, crossings

    def Paint(self):
        global BigFont, FontName, FontSize, BigFontSize, PlotFrameColor

        if self.dirty:
            if BigFont == None:
                BigFont = pygame.font.SysFont(FontName, BigFontSize)

            self.surface.fill(BgColor)

            # labels to be post-blitted on self.plotsurface
            self.plotlabels = []

            # Draw the plot frame
            pygame.draw.rect(self.surface, PlotFrameColor, self.rect, 1)
            if self.data.Count() > 1:
                # The main plot (position vs time)
                samples = self.data.Samples(1)
                end, crossings = self.plot(samples, self.data.Range(1), PosLineColor, PosNodeColor, 1, self.data.crossings)

                # Secondary plot (velocity)
                self.plot(self.data.Samples(2), self.data.Range(2), VelLineColor, VelNodeColor, 2)

                # Draw start and end times 
                label = Font.render('%3.1f' % (samples[0][0]), 1, PlotTextColor)
                labely = self.rect.bottom + 2
                self.surface.blit(label, (self.rect.left - label.get_width()/2, labely))
                label = Font.render('%3.1f' % (samples[-1][0]), 1, PlotTextColor)
                self.surface.blit(label, (self.rect.right - label.get_width()/2, labely))

                # Draw totals
                label = BigFont.render('Time=%4.1fms' % ((samples[-1][0] - samples[0][0])), 0, PlotTextColor)
                labely = self.rect.height - label.get_height() * 4 if end[1] < self.rect.height/2 else label.get_height()
                labelx = self.rect.width - label.get_width() - 20
                self.surface.blit(label, (labelx, labely))
                labely = labely + label.get_height()
                label = BigFont.render('Xings=%d' % (len(crossings)), 0, PlotTextColor)
                self.surface.blit(label, (labelx, labely))

                # Draw plotlabels
                for label in self.plotlabels:
                    self.plotsurface.blit(label[0], label[1])

            self.dirty = False

        return self.surface

class TextWin:
    surface = None
    rect = None
    skiplines = 0
    buffer = None
    global FontName, FontSize

    def __init__(self, buf, dimension):
        self.buffer = buf
        self.buffer.OnChange = self.BufferChanged
        self.Resize(dimension)
        self.skiplines = 0

    def BufferChanged(self):
        self.skiplines = 0

    def Resize(self, dimension):
        self.rect = pygame.Rect((0, 0), dimension)
        self.surface = pygame.Surface(dimension)

    def ScrollUp(self):
        if self.skiplines < self.buffer.Count() - 1:
            self.skiplines = self.skiplines + 1

    def ScrollDown(self):
        if self.skiplines > 0:
            self.skiplines = self.skiplines - 1

    def drawScrollbar(self, total, visible, offset):
        global ScrollBarColor
        if (total == 0) or (visible == 0):
            total, visible = 1, 1
        barHeight = int(round(self.rect.height * 1.0 * visible / total))
        barY = self.rect.height - int(round(self.rect.height * 1.0 * offset / total))
        pygame.draw.line(self.surface, ScrollBarColor, (self.rect.right - 3, barY), (self.rect.right - 3, barY - barHeight), 3)

    def Paint(self):
        global Font
        if Font == None:
            Font = pygame.font.SysFont(FontName, FontSize)
        self.surface.fill(TextWinBgColor)

        texty = self.rect.height - LineHeight
        skippy = self.skiplines
        visible = 0
        for line in self.buffer.Enumerate():
            if skippy > 0:
                skippy = skippy - 1
                continue
            visible = visible + 1
            garbage = Font.render(line, 1, TextWinFgColor)
            self.surface.blit(garbage, (0, texty))
            texty = texty - LineHeight
            if texty < 0:
                break
        self.drawScrollbar(self.buffer.Count(), visible, self.skiplines)
        return self.surface

def TextWinHeight():
    return Dimension[1] - SeparatorPosition

def PlotRect():
    return pygame.Rect(0, 5, Dimension[0], SeparatorPosition - 5)

def main(connection):
    global Running, SeparatorPosition, Dimension

    state = DEFULAT

    pygame.init()
    pygame.display.set_caption("Motori monitor")
    screen = pygame.display.set_mode(Dimension, pygame.HWSURFACE|pygame.DOUBLEBUF|pygame.RESIZABLE)
    clock = pygame.time.Clock() 
    Running = True

    protocol = DataProtocol()
    buffa = Buffer()
    graph = Graph(PlotRect().size, protocol)
    status = TextWin(buffa, (Dimension[0], TextWinHeight()))

    connection.Enable(True)

    repaint = True
    while Running:
        event = pygame.event.wait()
        if event.type == pygame.QUIT:
            Running = False
            connection.Close()
        else:
            if event.type == pygame.VIDEORESIZE:
                Dimension = event.dict['size']
                screen=pygame.display.set_mode(Dimension, pygame.HWSURFACE|pygame.DOUBLEBUF|pygame.RESIZABLE)
                if SeparatorPosition >= Dimension[1] - int(Dimension[1] * 0.1):
                    SeparatorPosition = Dimension[1] - int(Dimension[1] * 0.1)
                graph.Resize(PlotRect().size)
                status.Resize((Dimension[0], TextWinHeight()))
                repaint = True
            elif event.type == pygame.KEYDOWN:                
                if ((event.mod & (pygame.KMOD_LMETA | pygame.KMOD_RMETA)) != 0) and (event.key == pygame.K_q):
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                else:
                    connection.Send(event.unicode)
            elif event.type == SERIALEVENT:
                framestart = pygame.time.get_ticks()
                valid = True
                while pygame.time.get_ticks() - framestart < 250:
                    line = connection.ReceiveLine()
                    if line == None:
                        break
                    line = line.strip()
                    buffa.NewLine(line)
                    protocol.ProcessData(line)
                    repaint = True
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if (event.pos[1] >= SeparatorPosition - 1) and (event.pos[1] <= SeparatorPosition + 1):
                    state = RESIZE
                if event.button == 5:
                    status.ScrollDown()
                    repaint = True
                if event.button == 4:
                    status.ScrollUp()
                    repaint = True
            elif event.type == pygame.MOUSEBUTTONUP:
                    state = DEFULAT
            elif event.type == pygame.MOUSEMOTION:
                if state == DEFULAT:
                    if (event.pos[1] >= SeparatorPosition - 1) and (event.pos[1] <= SeparatorPosition + 1):
                        pygame.mouse.set_cursor(*pygame.cursors.broken_x)
                    else:
                        pygame.mouse.set_cursor(*pygame.cursors.arrow)
                        graph.MouseMove((event.pos[0] - PlotRect().left, event.pos[1] - PlotRect().top))
                elif state == RESIZE:
                    SeparatorPosition = event.pos[1]
                    graph.Resize(PlotRect().size)
                    status.Resize((Dimension[0], TextWinHeight()))
                repaint = True
            if repaint:
                screen.blit(graph.Paint(), PlotRect().topleft)
                screen.blit(status.Paint(), (0, SeparatorPosition))
                pygame.draw.line(screen, SeparatorColor, (0, SeparatorPosition - 1), (screen.get_width(), SeparatorPosition - 1), 3)
                pygame.display.flip()
                repaint = False

def usage(appname):
    print 'Usage: %s <serial_device> <serial_speed>' % appname
    print 'Example: %s /dev/tty.SLAB_USBtoUART 230400' % appname

if __name__=="__main__":
    if len(sys.argv) == 1:
        usage(sys.argv[0])
        sys.exit(1)
    device, speed = None, 9600
    if len(sys.argv) > 1:
        device = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            speed = int(sys.argv[2])
        except:
            print '%s does not look like an serial speed' % sys.argv[2]
            sys.exit(1)

    connection = None
    try:
        connection = SerialConnection(device, speed)
    except:
        print 'Could not open device %s with speed %s' % (device, speed)

    if connection == None:
        try:
            connection = FileConnection(device)
        except:
            print 'Could not open text file %s either' % (device)
            sys.exit(1)


    main(connection)
