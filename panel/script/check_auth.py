#coding: utf-8
import sys,os,time
os.chdir('/www/server/panel/')
sys.path.insert(0,"class/")
sys.path.insert(0,"class_v2/")
import public

public.writeFile('data/.is_pro.pl','True')
public.writeFile('data/panel_pro.pl','True')
