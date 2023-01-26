#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 13 14:57:29 2023

@author: freddy@linuxtribe.fr
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy import stats
import csv
import argparse
import numpy as np
from scipy.ndimage import gaussian_filter1d
import colorsys
import datetime

parser = argparse.ArgumentParser(
				prog = 'glycemia_basal_counselor.py',
				description = 'OpenSource tools that tries help with diabetes',
				epilog = 'Additionnal details available on https://github.com/ffrouin/myDiabby')

parser.add_argument("-f", "--mydiabbycsvfile", required=True, help='path to access myDiabby csv export file')
parser.add_argument("-n", "--name", type=str, required=True, help='patient name')
parser.add_argument("-ln", "--lastname", type=str, required=True, help='paient lastname')
parser.add_argument("-a", "--age", type=str, required=True, help='patient age')
parser.add_argument("-m", "--meals", type=str, required=True, help='time list of patient meals. Syntax is "07:00,12:00,16:00,19:00"')
parser.add_argument("-ip", "--insulinpump", type=str, required=False, help='patient insulin pump reference', default='na')
parser.add_argument("-u", "--unit", type=str, required=True, help='mg/dl, mmol/L')
parser.add_argument("-is", "--insulinsensitivity", type=int, required=False, help='patient insulin sensitivity', default=160)
parser.add_argument("-ir", "--insulinreference", type=str, required=False, help='patient insulin reference', default='na')
parser.add_argument("-il", "--insulinactivelength", type=int, required=True, help='patient insulin active length in seconds. Default is 2h (7200)', default=7200)
parser.add_argument("-gs", "--glucosesensor", type=str, required=False, help='patient glucose sensor reference', default='na')
parser.add_argument("-df", "--dateforward", type=int, default=15, help='number of days to look forward from now to proceed to glycemic profile analysis')
parser.add_argument("-sd", "--startdate", type=str, default='now', help='date to start analyze with, now() by default or YYYY/MM/DD')
parser.add_argument("-ecmd", "--enablemediandeviationcorrection", type=bool, default=False, help='experimental - process to correct deviation of data series')
parser.add_argument("-cmd", "--correctmediandeviation", type=int, default=30, help='experimental - max deviation target to reach until to stop data correction')

args = parser.parse_args()

def scale_lightness(rgb, scale_l):
    # convert rgb to hls
    h, l, s = colorsys.rgb_to_hls(*rgb)
    # manipulate h, l, s values and return as rgb
    return colorsys.hls_to_rgb(h, min(1, l * scale_l), s = s)

def hm2int(hm):
	return(int(hm.split(':')[0])*3600+int(hm.split(':')[1])*60)

def int2hm(i):
	h = int(i/3600)
	m = int((i-h*3600)/60)
	hm = str(h)+ 'h' + str(m)	
	return(hm)

def correctDeviation(data, target):
	d_max = target+1
	while (d_max>target):
		i=0
		d_max = 0
		for v in data:
			d = abs(data[i-1]-data[i])
			if d>d_max:
				d_max=d
			if i>0:
				data[i-1] = (data[i-1]+data[i])/2 
			i+=1
	return(data)


def lfunc(slope, intercept, x):
	return slope * x + intercept

def linear_regression(t_start, t_end, data):
	t0 = t_start
	t1 = t_end
	x_selection = []
	y_selection = []
	i = 0
	for x in glycemia_x:
		if (x>=t0 and x<=t1):
			x_selection.append(glycemia_x[i])
			y_selection.append(data[i])
		i+=1
	slope, intercept, r, p, std_err = stats.linregress(x_selection, y_selection)   
	segment = [lfunc(slope,intercept,x_selection[0]), lfunc(slope,intercept,x_selection[-1])]	
	return(segment) # return y values as a table for t_start and t_end x position 

def basalEfficientRanges(meals):
	range = []
	last = 0
	for m in meals:
		range.append([last, hm2int(m)])
		last = hm2int(m)+insulin_active_length
	range.append([last, 86400])
	return(range)

def basalEfficientSubRanges(ranges, r_step=300, r_scan_length=5400, r_min=900):
	positive = False
	subRanges = []
	last = 0
	init = False
	for r in ranges:
		init = True
		for i in range(r[0]+int(r_scan_length/2),r[1]-int(r_scan_length/2),r_step):
			seg = linear_regression(i-int(r_scan_length/2),i+int(r_scan_length/2), gaussian_filter1d(glycemia_median,sigma=s))
			if seg[1] > seg[0]:
				if not positive:
					positive = True
					if init:
						init = False
						if i - r[0] > r_min:
							subRanges.append([r[0], i])
					else:
						if i - last > r_min:
							subRanges.append([last,i])					
					last = i
			else:
				if positive:
					positive = False
					if init:
						init = False
						if i - r[0] > r_min:
							subRanges.append([r[0], i])
					else:
						if i - last > r_min:
							subRanges.append([last,i])
					last = i
		if r[-1] - last > r_min:
			subRanges.append([last, r[-1]])
	if ranges[-1][-1] - last > r_min:
		subRanges.append([last, ranges[-1][-1]])
	return(subRanges)

## start of main

# global vars

meals = args.meals.split(',')
insulin_active_length = args.insulinactivelength # secs
insulin_sensitivity = args.insulinsensitivity

glycemia_stats = {}
glycemia_x = []
glycemia_median = []
glycemia_mg_p10 = []
glycemia_mg_p25 = []
glycemia_mg_p75 = []
glycemia_mg_p90 = []
glycemia_min = []
glycemia_max = []

# x,y are arrays of arrays containing linear regressive segments to report on plot
x = []
y = []

advices_timeranges = []
advices_gdelta = []
advices_iquantity = []
advices_irate = []

# prepare myDiabby import of data

capture = False;
start_date = datetime.datetime.today() - datetime.timedelta(days=args.dateforward)
end_date = datetime.datetime.today()
if 'now' not in args.startdate:
	end_date = datetime.datetime.strptime(args.startdate, '%Y/%m/%d')
	start_date = datetime.datetime.strptime(args.startdate, '%Y/%m/%d') - datetime.timedelta(days=args.dateforward)

last_known_weight = 0
last_known_weight_date = ''
last_known_hba1c = 0
last_known_hba1c_date = ''
last_max_ketones = 0
last_max_ketones_date = ''

# proceed to myDiabby import

with open(args.mydiabbycsvfile, newline='') as mydiabby:
	mydiabby_export = csv.reader(mydiabby,delimiter=',')
	for mydiabby_line in mydiabby_export:
		t = str(mydiabby_line[1])
		
#		if args.date not in mydiabby_line[0]: # filtering mode
#			continue

		if str(start_date).split(" ")[0] in mydiabby_line[0]:
			capture = True
			
		if str(end_date).split(" ")[0] == mydiabby_line[0]:
			capture = False
		
		if not capture:
			continue
		
		# collect last known weight to report
		if mydiabby_line[13] != '':
			last_known_weight = mydiabby_line[13]
			last_known_weight_date = mydiabby_line[0]
		
		# collect last known hba1c to report
		if mydiabby_line[14] != '':
			last_known_hba1c = mydiabby_line[14]
			last_known_hba1c_date = mydiabby_line[0]	
		
		# collect max ketones seen in the capture period to report
		if mydiabby_line[15] != '':
			if float(mydiabby_line[15]) > last_max_ketones:
				last_max_ketones = float(mydiabby_line[15])
				last_max_ketones_date = mydiabby_line[0]
			
		if 'time' in t:
			continue
		glycemia = mydiabby_line[2]
		if glycemia == '':
			continue
	
		glycemia = float(mydiabby_line[2])
		if t not in glycemia_stats.keys():
			glycemia_stats[t] = []
		glycemia_stats[t].append(glycemia)

# proceed to median analysis against captured data

for t in sorted(glycemia_stats.keys()):
	glycemia_x.append(hm2int(t))
	glycemia_median.append(np.median(glycemia_stats[t]))
	glycemia_mg_p10.append(np.percentile(glycemia_stats[t],10))
	glycemia_mg_p25.append(np.percentile(glycemia_stats[t],25))
	glycemia_mg_p75.append(np.percentile(glycemia_stats[t],75))
	glycemia_mg_p90.append(np.percentile(glycemia_stats[t],90))
	glycemia_min.append(min(glycemia_stats[t]))
	glycemia_max.append(max(glycemia_stats[t]))

# if required by user, proceed to experimental deviation correction before to plot data

if args.enablemediandeviationcorrection:
	glycemia_median = correctDeviation(glycemia_median, args.correctmediandeviation)
	glycemia_min = correctDeviation(glycemia_min, args.correctmediandeviation)
	glycemia_max = correctDeviation(glycemia_max, args.correctmediandeviation)
	glycemia_mg_p10 = correctDeviation(glycemia_mg_p10, args.correctmediandeviation)
	glycemia_mg_p25 = correctDeviation(glycemia_mg_p25,args.correctmediandeviation)
	glycemia_mg_p75 = correctDeviation(glycemia_mg_p75,args.correctmediandeviation)
	glycemia_mg_p90 = correctDeviation(glycemia_mg_p90, args.correctmediandeviation)

# main graph labels

fig, ax = plt.subplots()
median_patch = mpatches.Patch(color='indigo', label='median', alpha=0.75)
mg_p25_75_patch = mpatches.Patch(color='blueviolet', label='25-75%', alpha=0.75)
mg_p10_90_patch = mpatches.Patch(color='violet', label='10-90%', alpha=0.75)
minmax_patch =  mpatches.Patch(color='mediumpurple', label='min-max', alpha=0.75)
ax.legend(handles=[median_patch,mg_p25_75_patch,mg_p10_90_patch,minmax_patch])
  
# main document warnings and report tables

plt.get_current_fig_manager().set_window_title('OpenSource Insulin Basal Counselor')
plt.suptitle("OpenSource Insulin Basal Counselor",fontsize=20)

plt.text(-11000,392,s="WARNINGS !!! DO NOT USE THIS TOOL WITH HEALTH DATA OLDER THAN 15 DAYS",color='red',fontsize=8)
plt.text(-11000,386,s="!!! DO NOT APPLY ALL RECOMMANDED CHANGES AT THE SAME TIME !!! ",color='red',fontsize=8)
plt.text(-11000,380,s="DISCUSS THE RESULTS WITH YOUR DOCTOR TO DEFINE WHAT TO DO FIRST",color='red',fontsize=8)

plt.text(4.5*3600,372,s="data start :          "+str(start_date),fontsize=7)
plt.text(4.5*3600,366,s="data end :           "+str(end_date),fontsize=7)
plt.text(4.5*3600,360,s="date:                   "+str(datetime.datetime.now()),fontsize=7)
plt.text(4.5*3600,354,s="data source:        "+args.mydiabbycsvfile,fontsize=7)

plt.text(9*3600,372,s="patient : "+args.name+" "+args.lastname,fontsize=7)
plt.text(9*3600,366,s="age : "+str(args.age)+ " years old",fontsize=7)
plt.text(9*3600,360,s="weight : "+str(last_known_weight)+"Kg ["+last_known_weight_date+"]",fontsize=7)


plt.text(12*3600,372,s="insulin pump : "+args.insulinpump,fontsize=7)
plt.text(12*3600,366,s="glucose sensor : "+args.glucosesensor,fontsize=7)

plt.text(15*3600,372,s="insulin sensitivity : "+str(args.insulinsensitivity)+" mg/dl for 1U",fontsize=7)
plt.text(15*3600,366,s="insulin active length : "+str(int(args.insulinactivelength/3600))+"h ["+args.insulinreference+"]",fontsize=7)
plt.text(15*3600,360,s="HbA1c : "+str(last_known_hba1c)+'% ['+last_known_hba1c_date+"]",fontsize=7)
if last_max_ketones > 0:
	plt.text(15*3600,354,s="max ketones over period : "+str(last_max_ketones)+" mmol/l ["+last_max_ketones_date+"]",fontsize=7)
else:
	plt.text(15*3600,354,s="max ketones over period : "+str(last_max_ketones)+" mmol/l [na]",fontsize=7)

plt.text(22*3600,392,s='author: Freddy Frouin <freddy@linuxtribe.fr>',fontsize=7)
plt.text(22*3600,386,s="revision : v0.8 build 20230126_01",fontsize=7)
plt.text(22*3600,380,s="created on 20230111",fontsize=7)
plt.text(22*3600,374,s="sources : https://github.com/ffrouin/myDiabby",fontsize=7)

plt.text(-11000,-20,s="The OpenSource Insulin Counseler takes patient meals time as entry data table and then it looks for the daily time ranges where the glucose",fontsize=7)
plt.text(-11000,-26,s="concentration in blood should be stable. In these areas, using a linear regressive process against the median values of glucose concentration",fontsize=7)
plt.text(-11000,-32,s="helps to evaluate how to modify the patient basal scheme. In this report, meals are planned at "+args.meals+" and we do exclude",fontsize=7)
plt.text(-11000,-38,s="2h after meals of processing as these are the areas where glucose concentration may not be stable due to the difference between insulin action",fontsize=7)
plt.text(-11000,-44,s="and the patient digestion of his meal (ie. glucose assimilation process and rates).",fontsize=7)
		 
plt.ylabel('glucose '+args.unit)
plt.ylim(0,350)
plt.yticks([0,50,70,100,150,180,200,250,300,350])

plt.xlabel('time')
plt.xticks(ticks=[0,3600,7200,10800,14400,18000,21600,25200,28800,32400,36000,\
				 39600,43200,46800,50400,54000,57600,61200,64800,68400,72000,\
				 75600,79200,82800,86400], labels=['0h00','1h00','2h00','3h00','4h00',
				 '5h00','6h00','7h00','8h00','9h00','10h00','11h00','12h00',\
				 '13h00','14h00','15h00','16h00','17h00','18h00','19h00',\
				 '20h00','21h00','22h00','23h00','24h00'])

plt.bar(-301,350,600,color='red',alpha=0.75)
plt.bar(-301,250,600,color='orange',alpha=0.75)
plt.bar(-301,179,600,color='lightgreen',alpha=0.75)
plt.bar(-301,70,600,color='lightblue',alpha=0.75)
plt.bar(-301,50,600,color='darkblue',alpha=0.75)

plt.bar(86701,350,600,color='red',alpha=0.75)
plt.bar(86701,250,600,color='orange',alpha=0.75)
plt.bar(86701,179,600,color='lightgreen',alpha=0.75)
plt.bar(86701,70,600,color='lightblue',alpha=0.75)
plt.bar(86701,50,600,color='darkblue',alpha=0.75)

plt.axhline(y=70, color="lightblue",linewidth=0.5,linestyle='dashed',alpha=0.75)
plt.axhline(y=180, color="orange",linewidth=0.5,linestyle='dashed',alpha=0.75)
plt.axhline(y=250, color="red",linewidth=0.5,linestyle='dashed',alpha=0.75)	

plt.grid(color='lightblue',alpha=0.25,axis='y')
	   
s=12

plt.fill_between(glycemia_x, gaussian_filter1d(glycemia_max, sigma=s), gaussian_filter1d(glycemia_min, sigma=s), interpolate=True, color='mediumpurple', alpha=0.25)
plt.fill_between(glycemia_x, gaussian_filter1d(glycemia_mg_p10, sigma=s), gaussian_filter1d(glycemia_mg_p90, sigma=s), interpolate=True, color='violet', alpha=0.25)
plt.fill_between(glycemia_x, gaussian_filter1d(glycemia_mg_p25,sigma=s), gaussian_filter1d(glycemia_mg_p75, sigma=s), interpolate=True, color='blueviolet', alpha=0.25)

plt.scatter(glycemia_x, glycemia_median, 0.1, color='indigo', alpha=0.8)

plt.plot(glycemia_x, gaussian_filter1d(glycemia_median, sigma=s), 3, color='indigo')

plt.plot(glycemia_x, gaussian_filter1d(glycemia_min, sigma=s), linewidth=0.2, color='mediumpurple',alpha=0.4,antialiased=True)
plt.plot(glycemia_x, gaussian_filter1d(glycemia_max, sigma=s), linewidth=0.2, color='mediumpurple',alpha=0.4,antialiased=True)
plt.plot(glycemia_x, gaussian_filter1d(glycemia_mg_p10, sigma=s), linewidth=0.2, color='violet',alpha=0.4,antialiased=True)
plt.plot(glycemia_x, gaussian_filter1d(glycemia_mg_p25, sigma=s), linewidth=0.2, color='blueviolet',alpha=0.4,antialiased=True)
plt.plot(glycemia_x, gaussian_filter1d(glycemia_mg_p75, sigma=s), linewidth=0.2, color='blueviolet',alpha=0.4,antialiased=True)
plt.plot(glycemia_x, gaussian_filter1d(glycemia_mg_p90, sigma=s), linewidth=0.2, color='violet',alpha=0.4,antialiased=True)


# use the linear regressive process against median values in order extract qdelta and calculate iquantity and irate

br = basalEfficientRanges(meals) #br for basal ranges
advices_timeranges = basalEfficientSubRanges(br)

for r in advices_timeranges:
	seg = linear_regression(r[0], r[1], glycemia_median)
	d = abs(((seg[1]-seg[0])/insulin_sensitivity)/((r[1]-r[0])/3600))
	if d < 0.025:
		continue
	x.append([r[0], r[1]])
	y.append(seg)
	advices_gdelta.append(seg[1]-seg[0])
	advices_iquantity.append((seg[1]-seg[0])/insulin_sensitivity)
	advices_irate.append(((seg[1]-seg[0])/insulin_sensitivity)/((r[1]-r[0])/3600))
	
# render advices to the main plot with its legend

i=0
for r in x:
	color=np.random.rand(3,)
	plt.plot(r,y[i],c=color)
	label = '';
	if advices_irate[i] > 0:
		label = str(int2hm(r[0])+"-"+int2hm(r[1])+" +"+f'{advices_irate[i]:.3f}'+"U/h")
	else:
		label = str(int2hm(r[0])+"-"+int2hm(r[1])+" "+f'{advices_irate[i]:.3f}'+"U/h")
	plt.text((r[0]+r[1])/2,y[i][-1]+50,s=label,fontsize=9,c=scale_lightness(color, 0.75))
	label = ''
	if (advices_gdelta[i] >0):
		label = '[+'
	label += f'{advices_gdelta[i]:.2f}' + args.unit + ' ' + f'{advices_iquantity[i]:.3f}' + 'U]'
	plt.text((r[0]+r[1])/2,y[i][-1]+43,s=label,fontsize=7, c=scale_lightness(color, 0.75))
	i+=1

plt.show()

