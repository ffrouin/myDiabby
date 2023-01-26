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
				prog = 'glycemia_bolus_counselor.py',
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
parser.add_argument("-gt", "--glycemiatarget", type=int, required=False, help='patient glycemia target', default=120)
parser.add_argument("-ir", "--insulinreference", type=str, required=False, help='patient insulin reference', default='na')
parser.add_argument("-il", "--insulinactivelength", type=int, required=False, help='patient insulin active length in seconds. Default is 2h (7200)', default=7200)
parser.add_argument("-gs", "--glucosesensor", type=str, required=False, help='patient glucose sensor reference', default='na')
parser.add_argument("-df", "--dateforward", type=int, default=15, help='number of days to look forward from now to proceed to glycemic profile analysis')
parser.add_argument("-sd", "--startdate", type=str, default='now', help='date to start analyze with, now() by default')
parser.add_argument("-ecmd", "--enablemediandeviationcorrection", type=bool, default=False, help='experimental - process to correct deviation of data series')
parser.add_argument("-cmd", "--correctmediandeviation", type=int, default=30, help='experimental - max deviation target to reach until to stop data correction')

args = parser.parse_args()

def scale_lightness(rgb, scale_l):
    # convert rgb to hls
    h, l, s = colorsys.rgb_to_hls(*rgb)
    # manipulate h, l, s values and return as rgb
    return colorsys.hls_to_rgb(h, min(1, l * scale_l), s = s)

def hm2int(hm):
	h = hm.split(':')[0].lstrip('0')
	m = hm.split(':')[1].lstrip('0')
	
	hi = 0
	mi = 0
	if not h == '':
		hi = int(h)
	if not m == '':
		mi = int(m)
		   
	return(hi*3600+mi*60)

def int2hm(i):
	h = int(i/3600)
	m = int((i-h*3600)/60)
	hm = ''
	if h<10:
		hm += '0'
	hm += str(h) + ':'
	if m<10:	
		hm += '0'		
	hm += str(m)
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

def select_data(t_start, t_end, data):
	t0 = t_start
	t1 = t_end
	x_selection = []
	y_selection = []	
	i = 0
	for x in glycemia_bolus_x:
		if (x>=t0 and x<=t1):
			x_selection.append(glycemia_bolus_x[i])
			y_selection.append(data[i])
		i+=1
	selection = [x_selection, y_selection]
	return(selection)

## start of main

# global vars

meals = args.meals.split(',')
insulin_active_length = args.insulinactivelength # secs
insulin_sensitivity = args.insulinsensitivity # 

glycemia_stats = {}
glycemia_x = []
glycemia_median = []
glycemia_mg_p10 = []
glycemia_mg_p25 = []
glycemia_mg_p75 = []
glycemia_mg_p90 = []
glycemia_min = []
glycemia_max = []

glycemia_bolus = {}
glycemia_bolus_high = {}
glycemia_bolus_low = {}
glycemia_bolus_x = []
glycemia_bolus_median = []
glycemia_bolus_median_high = []
glycemia_bolus_median_low = []

bolus_meal_carb = []
bolus_meal_iq = []

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

bolus_start = 0
bolus_start_glycemia = 0
bolus_carb = 0
bolus_iq = 0

# proceed to myDiabby import

with open(args.mydiabbycsvfile, newline='') as mydiabby:
	mydiabby_export = csv.reader(mydiabby,delimiter=',')
	for mydiabby_line in mydiabby_export:
		t = str(mydiabby_line[1])
						
		if 'time' in t:
			continue
		
#		if args.date not in mydiabby_line[0]: # filtering mode
#			continue

		if str(start_date).split(" ")[0] == mydiabby_line[0]:
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
		
		meal_range = False
		meal_index = 0
		for r in meals:
			if hm2int(t) >= hm2int(r)-3600 and  hm2int(t) <= hm2int(r)+insulin_active_length+3600:
				meal_range = True
				break
			bolus_meal_carb.append([])
			bolus_meal_iq.append([])
			meal_index += 1
			
		if mydiabby_line[18] != '':
			bolus_carb = float(mydiabby_line[18])
			
		# check if a bolus is done
		if mydiabby_line[6] != '':
			bolus_start = hm2int(mydiabby_line[1])
			bolus_iq = float(mydiabby_line[6])
			continue

		glycemia = mydiabby_line[2]
		if glycemia == '':
			continue
		glycemia = float(glycemia)
		
		if t not in glycemia_stats.keys():
			glycemia_stats[t] = []
		glycemia_stats[t].append(glycemia)
	
		if meal_range and bolus_start > 0:	
			# only include insulin active length after bolus data
			if hm2int(mydiabby_line[1]) > bolus_start+insulin_active_length:
				bolus_meal_carb[meal_index].append(bolus_carb)
				bolus_meal_iq[meal_index].append(bolus_iq)   
				bolus_start = 0
				bolus_carb = 0
				bolus_iq = 0
				continue
			d = hm2int(meals[meal_index])
			delta = hm2int(t)-bolus_start
			if delta <= 300:
				bolus_start_glycemia = glycemia
			d += delta
			if d >= 0:
				if bolus_start_glycemia > args.glycemiatarget-insulin_sensitivity/10 and bolus_start_glycemia < args.glycemiatarget+insulin_sensitivity/10:
					if  int2hm(d) not in glycemia_bolus.keys():
						glycemia_bolus[int2hm(d)] = []
					glycemia_bolus[int2hm(d)].append(glycemia)


# proceed to median analysis against captured data

for t in sorted(glycemia_bolus.keys()):
	glycemia_bolus_x.append(hm2int(t))
	glycemia_bolus_median.append(np.median(glycemia_bolus[t]))

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
median_sync_bolus_patch = mpatches.Patch(color='red', label='median of time sync bolus starting at '+str(args.glycemiatarget)+args.unit+' +/-'+f'{insulin_sensitivity/10:0.2f}'+args.unit, alpha=0.75)
ax.legend(handles=[median_patch,median_sync_bolus_patch])
  
# main document warnings and report tables

plt.get_current_fig_manager().set_window_title('OpenSource Insulin Bolus Counselor')
plt.suptitle("OpenSource Insulin Bolus Counselor",fontsize=20)

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

plt.text(15*3600,372,s="insulin sensitivity : "+str(args.insulinsensitivity)+" "+args.unit+" for 1U",fontsize=7)
plt.text(15*3600,366,s="insulin active length : "+str(int(args.insulinactivelength/3600))+"h ["+args.insulinreference+"]",fontsize=7)
plt.text(15*3600,360,s="HbA1c : "+str(last_known_hba1c)+'% ['+last_known_hba1c_date+"]",fontsize=7)
if last_max_ketones > 0:
	plt.text(15*3600,354,s="max ketones over period : "+str(last_max_ketones)+" mmol/l ["+last_max_ketones_date+"]",fontsize=7)
else:
	plt.text(15*3600,354,s="max ketones over period : "+str(last_max_ketones)+" mmol/l [na]",fontsize=7)

plt.text(22*3600,392,s='author: Freddy Frouin <freddy@linuxtribe.fr>',fontsize=7)
plt.text(22*3600,386,s="revision : v0.3 build 20230126_01",fontsize=7)
plt.text(22*3600,380,s="created on 20230116",fontsize=7)
plt.text(22*3600,374,s="sources : https://github.com/ffrouin/myDiabby",fontsize=7)

plt.text(-11000,-20,s="The OpenSource Insulin Bolus Counseler takes patient meals time as entry data table and then it starts synchronize all bolus data series for each meal.",fontsize=7)
plt.text(-11000,-26,s="It then select all bolus data series that did start close to the glycemia target (+/- 10% of patient insulin sensitivity) to make sure to analize",fontsize=7)
plt.text(-11000,-32,s="the quantity of insulin supplied to the patient against his meal carbone count. The bolus data series starting outside the target range could then",fontsize=7)
plt.text(-11000,-38,s="be analized to evaluate patient insulin sensitivity (not yet included in report). In this report, meals are planned at "+args.meals,fontsize=7)
#plt.text(-11000,-44,s="",fontsize=7)
		 
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
plt.scatter(glycemia_bolus_x, glycemia_bolus_median, 0.1, color='red', alpha=1.0)

plt.plot(glycemia_x, gaussian_filter1d(glycemia_median, sigma=s), 3, color='indigo')


i = 0
for r in meals:
	c =np.random.rand(3,)
	plt.plot(select_data(hm2int(r),hm2int(r)+insulin_active_length, glycemia_bolus_x)[0], gaussian_filter1d(select_data(hm2int(r),hm2int(r)+insulin_active_length, glycemia_bolus_median)[1], sigma=s), 3, color='red')	
	gdelta = gaussian_filter1d(select_data(hm2int(r),hm2int(r)+insulin_active_length, glycemia_bolus_median),sigma=s)[1][-1]-gaussian_filter1d(select_data(hm2int(r),hm2int(r)+insulin_active_length, glycemia_bolus_median),sigma=s)[1][0]
	iq = gdelta/insulin_sensitivity
	ir = iq/(insulin_active_length/3600)
	label = r+"-"+int2hm(hm2int(r)+insulin_active_length)
	label2 = ''
	if gdelta > 0:
		label2 = '+'+f'{gdelta:.3f}'+" "+args.unit
	else:
		label2 = f'{gdelta:.3f}' +" "+args.unit
	if iq > 0:
		label2 += ' +'+f'{iq:.3f}'+"U"
	else:
		label2 += ' '+f'{iq:.3f}'+"U"
	if ir > 0:
		label3 = "Basal +"+f'{ir:.3f}'+"U/h"
	else:
		label3 = "Basal "+f'{ir:.3f}'+"U/h"
	
	#label4 = "Bolus "+f'{np.median(bolus_meal_carb[i])/np.median(bolus_meal_iq[i]):0.1f}'+"g/U"
	label4 = "Bolus "
	rdelta = np.median(bolus_meal_carb[i])/(np.median(bolus_meal_iq[i])+iq)-np.median(bolus_meal_carb[i])/np.median(bolus_meal_iq[i])
	if rdelta > 0:
		label4 += " +"+f'{rdelta:0.1f}'+'g/U'
	else:
		label4 += " "+f'{rdelta:0.1f}'+'g/U'
	plt.text(hm2int(r),300,s=label,fontsize=9,c='red')
	plt.text(hm2int(r),294,s=label2,fontsize=9,c='red')
	plt.text(hm2int(r),288,s=label3,fontsize=9,c='red')
	plt.text(hm2int(r),282,s=label4,fontsize=9,c='red')
	i+=1
	
#plt.plot(glycemia_x, gaussian_filter1d(glycemia_min, sigma=s), linewidth=0.2, color='mediumpurple',alpha=0.4,antialiased=True)
#plt.plot(glycemia_x, gaussian_filter1d(glycemia_max, sigma=s), linewidth=0.2, color='mediumpurple',alpha=0.4,antialiased=True)
#plt.plot(glycemia_x, gaussian_filter1d(glycemia_mg_p10, sigma=s), linewidth=0.2, color='violet',alpha=0.4,antialiased=True)
#plt.plot(glycemia_x, gaussian_filter1d(glycemia_mg_p25, sigma=s), linewidth=0.2, color='blueviolet',alpha=0.4,antialiased=True)
#plt.plot(glycemia_x, gaussian_filter1d(glycemia_mg_p75, sigma=s), linewidth=0.2, color='blueviolet',alpha=0.4,antialiased=True)
#plt.plot(glycemia_x, gaussian_filter1d(glycemia_mg_p90, sigma=s), linewidth=0.2, color='violet',alpha=0.4,antialiased=True)

plt.show()

