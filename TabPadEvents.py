#!/usr/bin/python3

import subprocess
import time
import evdev
from evdev import ecodes
from TabPadConfig import *
import multiprocessing
from pymouse import PyMouse
from pykeyboard import PyKeyboard
import itertools
from math import sqrt

class newProcess (multiprocessing.Process):
	def __init__(self, processID, name, touch_panel, screen_width, screen_height):
		super(newProcess, self).__init__()
		self.processID = processID
		self.name = name
		self.daemon = True
		self.touch_panel = touch_panel
		self.no_device_found = True
		self.screen_width = screen_width
		self.screen_height= screen_height
		self.min_x, self.max_x = None, None
		self.min_y, self.max_y = None, None
		self.res_x, self.res_y = None, None
		self.keydown_list = []
		self.devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
		# print (self.devices)
		self.inputsetup()

	def run(self):
		print ("\nStarting: " + self.name)
		self.eventloop()

	def inputsetup(self):
		for d in self.devices:
			# print(d.fn, d.name, device.phys)
			# print (d.name)
			if (d.name == self.touch_panel):
				input_node = d.fn
				self.set_min_max_values(d)
				self.no_device_found = False

		if self.no_device_found == True:
			print ("No touch input detected.")
			print ("Please make sure you have entered correct touch panel name in user settings.")
			print ("And that you are running the app with root access.")
			print ("Quitting in 10 seconds.")
			time.sleep(10)
			quit()
			sys.exit(1)

		self.device = evdev.InputDevice(input_node)

	def eventloop(self):
		touch_time = None
		lift_time = None
		x_abs_val = None
		y_abs_val = None
		finger0_coords = None
		finger1_coords = None
		self.keyup_trigger_flag = False
		self.keydown_list = []
		self.button_geometry = self.set_button_area()
		self.current_orientation = self.device_orientation()
		self.xdotool = "xdotool"
		self.py_mouse = PyMouse()
		self.py_keyboard = PyKeyboard()
		self.set_input_type()
		
		for ev in self.device.read_loop():
			# print (evdev.util.categorize(ev))
			if ev.code == 330 and ev.value == 1:
				self.keyup_trigger_flag = False

			if ev.code == 330 and ev.value == 0:
				lift_time = ev.timestamp()
			else:
				lift_time = None

			if ev.code == 53:
				if ev.value > 0:
					x_abs_val = ev.value
			if ev.code == 54:
				if ev.value > 0:
					y_abs_val = ev.value

			if lift_time != None:
				self.trigger_key_up()
				self.keyup_trigger_flag = True

			if x_abs_val != None and y_abs_val != None:
				if self.keyup_trigger_flag == False:
					self.compare_coords(*(self.convert_absolute_values((x_abs_val, y_abs_val))))

	def percentconvertor(self, val, dimension):
		val = int(round((dimension * val)/100))
		return val

	def compare_coords(self, actual_x, actual_y):
		l = []
		main_button_flag = False
		for v in self.button_geometry[0]:
			if actual_x >= v[1] and actual_x <= v[2]:
				if actual_y >= v[3] and actual_y <= v[4]:
					l.append(button_layout[v[0]][2])
					main_button_flag = True
		if not main_button_flag:
			for s in self.button_geometry[1]:
				if actual_x >= s[2] and actual_x <= s[3]:
					if actual_y >= s[4] and actual_y <= s[5]:
						l.append(button_layout[s[0]][2])
						l.append(button_layout[s[1]][2])
		if l:
			if len(l) > 1:
				l = self.remove_duplicates_in_array(l)
			self.command_executor(l, actual_x, actual_y)
		else:
			self.trigger_key_up(actual_x, actual_y)
		main_button_flag = False

	def command_executor(self, command_array, x, y):
		# self.keydown_list = []
		for c in command_array:
			if c:
				if not c in self.keydown_list:
					self.execute_keypress(c, "down", x, y)
					self.keydown_list.append(c)

	def remove_duplicates_in_array(self, array):
		array = sorted(array)
		a = list(array for array, _ in itertools.groupby(array))
		return a

	def convert_absolute_values(self, value):
		if coord_hack:
			if self.current_orientation == "normal":
				xc = value[0]
				yc = value[1]
			elif self.current_orientation == "inverted":
				xc = abs(self.max_x - value[0])
				yc = abs(self.max_y - value[1])
			elif self.current_orientation == "left":
				xc = abs(self.max_x - value[1])
				yc = value[0]
			elif self.current_orientation == "right":
				xc = value[1]
				yc = abs(self.max_y - value[0])
			else:
				xc = value[0]
				yc = value[1]
		else:
			xc = value[0]
			yc = value[1]

		xc = (xc - self.min_x) * self.screen_width / (self.max_x - self.min_x + 1)
		yc = (yc - self.min_y) * self.screen_height / (self.max_y - self.min_y + 1)
		xc = int(round(xc))
		yc = int(round(yc))

		if overlay_x_position < self.screen_width:
			xc = xc - overlay_x_position
			if xc < 0:
				xc = 0
		if overlay_y_position < self.screen_height:
			yc = yc - overlay_y_position
			if yc < 0:
				yc = 0
		# print (xc, yc)
		return (xc, yc)

	def device_orientation(self):
		c = "echo $(xinput list-props '" + self.touch_panel \
		+ "'| grep 'Coordinate Transformation Matrix' | sed 's/.*://')"
		ctm = self.get_bash_output(c)
		ctm = ctm.split(", ")
		ctm = [int(float(i)) for i in ctm]

		orientation = "xrandr -q|grep -v dis|grep con|awk '{print $5}'"
		orientation = self.get_bash_output(orientation)

		if ctm == [1, 0, 0, 0, 1, 0, 0, 0, 1] or orientation == "normal":
			c = "normal"
		if ctm == [-1, 0, 1, 0, -1, 1, 0, 0, 1] or orientation == "inverted":
			c = "inverted"
		if ctm == [0, -1, 1, 1, 0, 0, 0, 0, 1] or orientation == "left":
			c = "left"
		if ctm == [0, 1, 0, -1, 0, 1, 0, 0, 1] or orientation == "right":
			c = "right"
		return c

	def get_bash_output(self, cmnd):
		output = subprocess.Popen(cmnd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True ).communicate()
		output = str(output[0]).strip("\\n'")
		output = output.strip("'b")
		return output

	def kill_process(self):
		self.trigger_key_up()
		time.sleep(1)
		for p in multiprocessing.active_children():
			p.terminate()
		self.terminate()
		print ("\nTerminated: " + self.name)

	def set_min_max_values(self, device):
		d = device.capabilities()
		for p in d:
			if p == 3:
				for v in d[p]:
					if v[0] == 0 and ecodes.ABS[v[0]] == "ABS_X":
						self.min_x, self.max_x = v[1][1], v[1][2]
						self.res_x = v[1][-1]
					if v[0] == 1 and ecodes.ABS[v[0]] == "ABS_Y":
						self.min_y, self.max_y = v[1][1], v[1][2]
						self.res_y = v[1][-1]
		# print (self.min_x, self.max_x, self.res_x)
		# print (self.min_y, self.max_y, self.res_y)

	def set_button_area(self):
		button_geometry = []
		square_list = []
		for k, v in button_layout.items():
			self.x_start_pos = self.percentconvertor(v[0], overlay_width) - coord_adjustment_factor
			self.x_end_pos = self.x_start_pos + v[4][0] + (2 * coord_adjustment_factor)
			self.y_start_pos = self.percentconvertor(v[1], overlay_height) - coord_adjustment_factor
			self.y_end_pos = self.y_start_pos + v[4][1] + (2 * coord_adjustment_factor)
			button_geometry.append((k, self.x_start_pos, self.x_end_pos, self.y_start_pos, self.y_end_pos))
		
		for a, b in itertools.combinations(button_geometry, 2):
			xcenter1 = int(round((a[1] + a[2])/2))
			ycenter1 = int(round((a[3] + a[4])/2))
			xcenter2 = int(round((b[1] + b[2])/2))
			ycenter2 = int(round((b[3] + b[4])/2))
			circle1 = (xcenter1, ycenter1, circle_radius)
			circle2 = (xcenter2, ycenter2, circle_radius)
			center = self.circle_intersection_center(circle1, circle2)
			if center != None:
				k1 = a[0]
				k2 = b[0]
				square = self.square_coords(center[0], center[1], square_arm)
				square_list.append((k1, k2, *square))
		return button_geometry, square_list

	def trigger_key_up(self, x=0, y=0):
		if self.keydown_list:
			for i in self.keydown_list:
				self.execute_keypress(i, 'up', x, y)
			self.keydown_list = []

	def set_input_type(self):
		if input_method == "xdotool":
			self.keydown_string ="keydown"
			self.keyup_string = "keyup"
			self.mousedown_string = "mousedown"
			self.mouseup_string = "mouseup"
		if input_method == "pyuserinput":
			self.keydown_string ="press_key"
			self.keyup_string = "release_key"
			self.mousedown_string = "press"
			self.mouseup_string = "release"

	def modify_keys(self, input_list, input_type):
		if input_list[0] == "key" and input_type == "down":
			input_list[0] = self.keydown_string
		if input_list[0] == "key" and input_type == "up":
			input_list[0] = self.keyup_string
		if input_list[0] == "click" and input_type == "down":
			input_list[0] = self.mousedown_string
		if input_list[0] == "click" and input_type == "up":
			input_list[0] = self.mouseup_string
		return input_list

	def execute_keypress(self, cmnd, keytype, x, y):
		c = list(cmnd)
		if c:
			c = self.modify_keys(c, keytype)
			if input_method == "xdotool":
				c.insert(0, self.xdotool)
				subprocess.Popen(c, stdout=subprocess.PIPE)
			if input_method == "pyuserinput":
				if c[0][-3:] == "key":
					if c[0] == "press_key":
						self.py_keyboard.press_key(c[1])
					else:
						self.py_keyboard.release_key(c[1])
				if c[0] == "press":
					self.py_mouse.press(x, y, int(c[1]))
				if c[0] == "release":
					self.py_mouse.release(x, y, int(c[1]))

	def circle_intersection_center(self, circle1, circle2):
		x1,y1,r1 = circle1
		x2,y2,r2 = circle2
		dx,dy = x2-x1,y2-y1
		d = sqrt(dx*dx+dy*dy)
		if d > r1+r2:
			# print ("No solutions, the circles are separate.")
			return None
		if d < abs(r1-r2):
			# print ("No solutions, one circle is contained within the other")
			return None
		if d == 0 and r1 == r2:
			# print ("Circles are coincident and there are an infinite number of solutions")
			return None
		a = (r1*r1-r2*r2+d*d)/(2*d)
		h = sqrt(r1*r1-a*a)
		xm = x1 + a*dx/d
		ym = y1 + a*dy/d
		xs1 = xm + h*dy/d
		xs2 = xm - h*dy/d
		ys1 = ym - h*dx/d
		ys2 = ym + h*dx/d
		centerx = int(round((xs1+xs2)/2))
		centery = int(round((ys1+ys2)/2))
		center = (centerx, centery)
		return center

	def square_coords(self, x, y, side):
		x_start_pos = int(round(x - (side / 2)))
		x_end_pos = int(round(x + (side / 2)))
		y_start_pos = int(round(y - (side / 2)))
		y_end_pos = int(round(y + (side / 2)))
		return (x_start_pos, x_end_pos, y_start_pos, y_end_pos)