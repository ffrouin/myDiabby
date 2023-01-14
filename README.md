# myDiabby
OpenSource tools to try help with Diabete

## description
The OpenSource Insulin Counseler takes patient meals time as entry data table and then it looks for the daily time ranges where the glucose
concentration in blood should be stable. In these areas, using a linear regressive process against the median values of glucose concentration
helps to evaluate how to modify the patient basal scheme. In this example, meals are planned at 7am 12am 16pm and 19pm and we do exclude
2h after meals of processing as this are the areas where glucose concentration may not be stable due to the difference between insulin action
and the patient digestion of his meal (ie. glucose assimilation process and rates).

## exemple
![OpenSource Insulin Counselor](20230114_OpenSourceInsulinBasalCounselor.png)
