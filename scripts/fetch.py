import random
from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import requests
import pandas as pd
import urllib.parse

from scripts.helpers import strip_val, get_value_by_path


BROWSER = 'chrome'

def create_session(email, password):
    if BROWSER == 'chrome':
        driver = webdriver.Chrome()
    elif BROWSER == 'edge':
        driver = webdriver.Edge()

    driver.get('https://www.linkedin.com/checkpoint/rm/sign-in-another-account')
    time.sleep(1)
    driver.find_element(By.ID, 'username').send_keys(email)
    driver.find_element(By.ID, 'password').send_keys(password)
    driver.find_element(By.XPATH, '//*[@id="organic-div"]/form/div[4]/button').click()
    # //*[@id="organic-div"]/form/div[4]/button
    time.sleep(10)
    # input('Press ENTER after a successful login for "{}": '.format(email))
    driver.get('https://www.linkedin.com/jobs/search/?')
    time.sleep(1)
    cookies = driver.get_cookies()
    driver.quit()
    session = requests.Session()
    for cookie in cookies:
        session.cookies.set(cookie['name'], cookie['value'])
    return session

def get_logins(method):
    logins = pd.read_csv('logins.csv')
    logins = logins[logins['method'] == method]
    emails = logins['emails'].tolist()
    passwords = logins['passwords'].tolist()
    return emails, passwords
def parse_count(count_result):
    if count_result.status_code != 200:
        raise Exception('Status code {} for search\nText: {}'.format(count_result.status_code, count_result.text))
    results = count_result.json()['data']['elements'][0]['secondaryFilterGroups']
    count = -1
    for result in results:
        for filter in result['filters']:
            if filter.get("viewImpressionEventName","") == "search_filter_timepostedrange_view":
                count = filter['secondaryFilterValues'][0]['count']
                break
        if count != -1:
            break
    return max(count,0)
class JobSearchRetriever:
    def __init__(self, geo_id='103644278', keyword='prompt engineer'):
        self.filter_link = f"https://www.linkedin.com/voyager/api/voyagerJobsDashSearchFilterClustersResource?decorationId=com.linkedin.voyager.dash.deco.search.SearchFilterCluster-44&q=filters&query=(origin:JOB_SEARCH_PAGE_LOCATION_AUTOCOMPLETE,keywords:%22{{keyword}}%22,locationUnion:(geoId:{{geo_id}}),spellCorrectionEnabled:true)"
        self.job_search_link = f"https://www.linkedin.com/voyager/api/voyagerJobsDashJobCards?decorationId=com.linkedin.voyager.dash.deco.jobs.search.JobSearchCardsCollection-216&count={{count}}&q=jobSearch&query=(origin:JOBS_HOME_SEARCH_BUTTON,keywords:%22{{keyword}}%22,locationUnion:(geoId:{{geo_id}}),spellCorrectionEnabled:true)&start=0"
        
        self.geo_id = geo_id
        self.keyword = keyword
        
        emails, passwords = get_logins('search')
        self.sessions = [create_session(email, password) for email, password in zip(emails, passwords)]
        self.session_index = 0
        
        self.headers = [{
            'Authority': 'www.linkedin.com',
            'Method': 'GET',
            'Scheme': 'https',
            'Accept': 'application/vnd.linkedin.normalized+json+2.1',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cookie': "; ".join([f"{key}={value}" for key, value in session.cookies.items()]),
            'Csrf-Token': session.cookies.get('JSESSIONID').strip('"'),
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
            'X-Li-Track': '{"clientVersion":"1.13.5589","mpVersion":"1.13.5589","osName":"web","timezoneOffset":-7,"timezone":"America/Los_Angeles","deviceFormFactor":"DESKTOP","mpName":"voyager-web","displayDensity":1,"displayWidth":360,"displayHeight":800}'
        } for session in self.sessions]

    def get_jobs(self):
        job_ids = {}
        # URL encode the keyword
        encoded_keyword = urllib.parse.quote(self.keyword)
        
        # Update links with current keyword
        filter_link = self.filter_link.format(keyword=encoded_keyword, geo_id=self.geo_id)
        count_result = self.sessions[self.session_index].get(filter_link, headers=self.headers[self.session_index])
        count = parse_count(count_result)
        
        job_search_link = self.job_search_link.format(count=count, keyword=encoded_keyword, geo_id=self.geo_id)
        results = self.sessions[self.session_index].get(job_search_link, headers=self.headers[self.session_index])

        self.session_index = (self.session_index + 1) % len(self.sessions)

        if results.status_code != 200:
            raise Exception('Status code {} for search\nText: {}'.format(results.status_code, results.text))
        results = results.json()
        job_ids = {}

        for r in results['included']:
            if r['$type'] == 'com.linkedin.voyager.dash.jobs.JobPostingCard' and 'referenceId' in r:
                job_id = int(strip_val(r['jobPostingUrn'], 1))
                job_ids[job_id] = {
                    'sponsored': False,
                    'title': r.get('jobPostingTitle'),
                    'search_keyword': self.keyword  # Add the search keyword
                }
                for x in r['footerItems']:
                    if x.get('type') == 'PROMOTED':
                        job_ids[job_id]['sponsored'] = True
                        break

        return job_ids

class JobDetailRetriever:
    def __init__(self):
        self.error_count = 0
        self.job_details_link = "https://www.linkedin.com/voyager/api/jobs/jobPostings/{}?decorationId=com.linkedin.voyager.deco.jobs.web.shared.WebFullJobPosting-65"
        emails, passwords = get_logins('details')
        self.emails = emails
        self.sessions = [create_session(email, password) for email, password in zip(emails, passwords)]
        self.session_index = 0
        self.variable_paths = pd.read_csv('json_paths/data_variables.csv')

        self.headers = [{
            'Authority': 'www.linkedin.com',
            'Method': 'GET',
            'Path': '/voyager/api/search/hits?decorationId=com.linkedin.voyager.deco.jserp.WebJobSearchHitWithSalary-25&count=25&filters=List(sortBy-%3EDD,resultType-%3EJOBS)&origin=JOB_SEARCH_PAGE_JOB_FILTER&q=jserpFilters&queryContext=List(primaryHitType-%3EJOBS,spellCorrectionEnabled-%3Etrue)&start=0&topNRequestedFlavors=List(HIDDEN_GEM,IN_NETWORK,SCHOOL_RECRUIT,COMPANY_RECRUIT,SALARY,JOB_SEEKER_QUALIFIED,PRE_SCREENING_QUESTIONS,SKILL_ASSESSMENTS,ACTIVELY_HIRING_COMPANY,TOP_APPLICANT)',
            'Scheme': 'https',
            'Accept': 'application/vnd.linkedin.normalized+json+2.1',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cookie': "; ".join([f"{key}={value}" for key, value in session.cookies.items()]),
            'Csrf-Token': session.cookies.get('JSESSIONID').strip('"'),
            # 'TE': 'Trailers',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
            # 'X-Li-Track': '{"clientVersion":"1.12.7990","mpVersion":"1.12.7990","osName":"web","timezoneOffset":-7,"timezone":"America/Los_Angeles","deviceFormFactor":"DESKTOP","mpName":"voyager-web","displayDensity":1,"displayWidth":1920,"displayHeight":1080}'
            'X-Li-Track': '{"clientVersion":"1.13.5589","mpVersion":"1.13.5589","osName":"web","timezoneOffset":-7,"timezone":"America/Los_Angeles","deviceFormFactor":"DESKTOP","mpName":"voyager-web","displayDensity":1,"displayWidth":360,"displayHeight":800}'
        } for session in self.sessions]

        # self.proxies = [{'http': f'http://{proxy}', 'https': f'http://{proxy}'} for proxy in []]


    def get_job_details(self, job_ids):
        job_details = {}
        for job_id in job_ids:
            error = False
            try:
                details = self.sessions[self.session_index].get(self.job_details_link.format(job_id), headers=self.headers[self.session_index])#, proxies=self.proxies[self.session_index], timeout=5)
            except requests.exceptions.Timeout:
                print('Timeout for job {}'.format(job_id))
                error = True
            if details.status_code != 200:
                job_details[job_id] = -1
                print('Status code {} for job {} with account {}\nText: {}'.format(details.status_code, job_id, self.emails[self.session_index], details.text))
                error = True
            if error:
                self.error_count += 1
                if self.error_count > 10:
                    raise Exception('Too many errors')
            else:
                self.error_count = 0
                job_details[job_id] = details.json()
                print('Job {} done'.format(job_id))
            self.session_index = (self.session_index + 1) % len(self.sessions)
            time.sleep(.3)
        return job_details

# https://proxy2.webshare.io/register?

