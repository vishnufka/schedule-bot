
#!/usr/bin/env python3

import os
import time
import re
import requests
import datetime
import slack


testing = False

# instantiate Slack client
slack_client = slack.WebClient(token=os.environ["SLACK_API_TOKEN"])
# starterbot's user ID in Slack: value is assigned after the bot starts up
starterbot_id = None

#slack params
channel_live = ""
channel_debug = ""

#float params
if (testing):
    now = datetime.datetime(2021,1,15).date()
else:
    now = datetime.datetime.now().date()
today = now.strftime("%Y-%m-%d")
today_as_date = datetime.datetime.strptime(today, "%Y-%m-%d").date()
today_as_words = now.strftime("%A %d %B %Y")
task_url = "https://api.float.com/v3/tasks?start_date="+today+"&end_date="+today+"&people_id="
people_url = "https://api.float.com/v3/people"
project_url = "https://api.float.com/v3/projects/"
client_url = "https://api.float.com/v3/clients/"
timeoffs_url = "https://api.float.com/v3/timeoffs?start_date="+today+"&end_date="+today
headers = {"Authorization":"Bearer " + os.environ["FLOAT_API_TOKEN"]}

def get_timeoffs():
    return requests.get(timeoffs_url,headers=headers).json()
    
def get_tasks(key):
    return requests.get(task_url+key,headers=headers).json()

def get_people():
    return requests.get(people_url,headers=headers).json()

def get_people_dict(people_response):
    people = {}
    for entry in people_response:
        if entry['active'] == 1:
            id = str(entry['people_id'])
            name = entry['name']
            people[id] = name
    return people

def get_people_dates(people_response, people):
    people_dates = {}
    for entry in people_response:
        id = str(entry['people_id'])
        if entry['start_date'] != None:
            start_date = datetime.datetime.strptime(entry['start_date'], "%Y-%m-%d").date()
        else:
            start_date = datetime.datetime(2000,1,1).date()
        if entry['end_date'] != None:
            end_date = datetime.datetime.strptime(entry['end_date'], "%Y-%m-%d").date()
        else:
            end_date = datetime.datetime(2100,1,1).date()
        people_dates[id] = {"start_date":start_date,"end_date":end_date}
    return people_dates

def post_activity():
    response = ""
    responses = {}
    timeoffs_response = get_timeoffs()
    people_response = get_people()
    people = get_people_dict(people_response)
    people_dates = get_people_dates(people_response, people)
    for key, person_name in people.items():
        if (people_dates[key]["start_date"] <= today_as_date and people_dates[key]["end_date"] >= today_as_date):
            pass
        else:
            continue
        #check holidays first as if true they won't have any work scheduled anyway
        full_schedule = False
        half_day_holiday = False
        #check each timeoff to see if the person is on holiday
        for i in range (0, len(timeoffs_response)):
            #this prevents a bug where holiday from people who have been
            #removed from float remains behind and causes an index error
            if not timeoffs_response[i]['people_ids']:
                continue
            else:
                person_id = timeoffs_response[i]['people_ids'][0]
            #if they match then check if full/half day and any notes
            if int(person_id) == int(key):
                if timeoffs_response[i]['full_day']:
                    time_off = " (all day)"
                    full_schedule = True
                else:
                    notes = ""
                    if len(timeoffs_response[i]['timeoff_notes']) > 0:
                        notes = " Notes: " + timeoffs_response[i]['timeoff_notes']
                    time_off = " (" + str(timeoffs_response[i]['hours']) + "hrs)" + notes
                    half_day_holiday = True
                responses.setdefault(timeoffs_response[i]['timeoff_type_name'], [])
                responses[timeoffs_response[i]['timeoff_type_name']].append(" - " + person_name + time_off)
        #if they're not on holiday then check the tasks for the day
        if not (full_schedule):
            task_response = get_tasks(key)
            #if nothing comes back they must be unscheduled
            if not task_response:
                if (person_name == "Manager 1" or person_name == "Manager 2" or person_name == "Manager 3"):
                    continue
                if (half_day_holiday):
                    responses.setdefault("Unscheduled", [])
                    responses["Unscheduled"].append(" - " + person_name + " (4hrs)")
                else:
                    responses.setdefault("Unscheduled", [])
                    responses["Unscheduled"].append(" - " + person_name + " (all day)")
                full_schedule = True
            #this is the tricky buggy part
            #repeat_state: 0 = none, 1 = weekly, 2 = monthly, 3 = fortnightly
            else:
                person_written = False
                for i in range (0, len(task_response)):
                    
                    start_date = datetime.datetime.strptime(task_response[i]['start_date'], "%Y-%m-%d").date()
                    end_date = datetime.datetime.strptime(task_response[i]['end_date'], "%Y-%m-%d").date()
                    repeat_state = int(task_response[i]['repeat_state'])
                    do_execute = False
                    if (start_date <= now and end_date >= now):
                        do_execute = True
                    
                    elif (repeat_state != 0):
                        repeat_end_date = datetime.datetime.strptime(task_response[i]['repeat_end_date'], "%Y-%m-%d").date()
                        while (end_date < repeat_end_date):
                            if (repeat_state == 1):
                                start_date = start_date + datetime.timedelta(days=7)
                                end_date = end_date + datetime.timedelta(days=7)
                            if (repeat_state == 2):
                                start_date = start_date + datetime.timedelta(months=1)
                                end_date = end_date + datetime.timedelta(months=1)   
                            if (repeat_state == 3):
                                start_date = start_date + datetime.timedelta(days=14)
                                end_date = end_date + datetime.timedelta(days=14)
                                
                            if (start_date <= now and end_date >= now):
                                do_execute = True
                    else:
                        do_execute = False
                        
                    if (do_execute):
                        
                        project_id = task_response[i]['project_id']
                        project_response = requests.get(project_url+str(project_id),headers=headers).json()
                        
                        client_id = project_response['client_id']
                        client_response = requests.get(client_url+str(client_id),headers=headers).json()
                        
                        notes = ""
                        if task_response[i]['notes'] != None and len(task_response[i]['notes']) > 0:
                            notes = " Notes: " + task_response[i]['notes']
                        
                        responses.setdefault(client_response['name'], [])
                        responses[client_response['name']].append(" - " + person_name + " (" + str(task_response[i]['hours']) + "hrs): " + task_response[i]['name'] + " - " + project_response['name'] + notes)
                        
                        person_written = True
                    
                #no valid tasks, must be unscheduled but check for half day holiday
                if not (person_written):
                    if (person_name == "Manager 1" or person_name == "Manager 2" or person_name == "Manager 3"):
                        continue
                    if (half_day_holiday):
                        responses.setdefault("Unscheduled", [])
                        responses["Unscheduled"].append(" - " + person_name + " (4hrs)")
                    else:
                        responses.setdefault("Unscheduled", [])
                        responses["Unscheduled"].append(" - " + person_name + " (all day)")
                       
    for client_key, value_array in responses.items():
        response += "\n*" + str(client_key) + "*"
        for i in range (0, len(value_array)):
            response += "\n\t" + value_array[i]
    
    response = "Activity for " + today_as_words + ":\n" + response
    
    if testing:
        current_channel = channel_debug
    else:
        current_channel = channel_live
    
    slack_client.chat_postMessage(
        channel=current_channel,
        text=response,
        as_user=True
    )


def lambda_handler(event, context):
    post_activity()
    return("Schedule Bot posted successfully!")
