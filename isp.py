#!/usr/bin/env python3
#coding: utf-8
__author__ = 'stsmith'

# isp_data_pollution: bandwidth-limited ISP data pollution 

# Copyright 2017 Steven T. Smith <steve dot t dot smith at gmail dot com>, GPL

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import datetime as dt, numpy as np, numpy.random as npr, os, random, requests, signal, tarfile, time
import urllib.request, urllib.robotparser as robotparser, urllib.parse as uprs
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from io import BytesIO
from faker import Factory

# nice this process
os.nice(15)

gb_per_month = 500		# How many gigabytes to pollute per month
max_links_cached = 100000	# Maximum number of links to cache for download
max_links_per_page = 200	# Maximum number of links to add per page
max_links_per_domain = 400	# Maximum number of links to add per domain
search_url = 'http://www.google.com/search'	# keep unencrypted for ISP DPI
wordsite_url = 'http://svnweb.freebsd.org/csrg/share/dict/words?view=co&content-type=text/plain'

blacklist_url = 'http://www.shallalist.de/Downloads/shallalist.tar.gz'
# Usage of the Shalla Blacklists:
# ===============================
#
# The Shalla Blacklists are property of Shalla Secure Services.
#
# This collection of url lists may be used for free for non
# commercial usage. This includes all kinds of private usage.
# The lists must not be given to any third party.

# tell my ISP that I use a really awful browser, along with random user agents (below)
user_agent = 'Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko'

# fix via override the read class method in RobotFileParser
# many sites will block access to robots.txt without a standard User-Agent header
class RobotFileParserUserAgent(robotparser.RobotFileParser):
    def read(self):
        """Reads the robots.txt URL and feeds it to the parser."""
        try:
            headers = {'User-Agent': user_agent, }
            request = urllib.request.Request(self.url, None, headers)
            f = urllib.request.urlopen(request)
            # f = urllib.request.urlopen(self.url)   #! original code
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                self.disallow_all = True
            elif err.code >= 400 and err.code < 500:
                self.allow_all = True
        else:
            raw = f.read()
            self.parse(raw.decode("utf-8").splitlines())

# Notes for the future:
# 1. The bandwidth usage is undoubtedly (much) smaller because gzip encoding is used
# 2. A lightweight proxy could be used for accurate bandwidth, and header editing

class ISPDataPollution:
    '''Re: https://www.eff.org/deeplinks/2017/03/senate-puts-isp-profits-over-your-privacy
 
I pay my ISP a lot for data usage every month. I typically don't use
all the bandwidth that I pay for.  If my ISP is going to sell my
private browsing habits, then I'm going to pollute my browsing with
noise and use all the bandwidth that I pay for. This method
accomplishes this.

If everyone uses all the data they've paid for to pollute their
browsing history, then perhaps ISPs will reconsider the business model
of selling customers' private browsing history.

The alternative of using a VPN or Tor merely pushes the issue onto to
the choice of VPN provider, complicates networking, and adds the
real issue of navigating captchas when appearing as a Tor exit node.

The crawler uses the Python requests and lxml.html libraries, is hardcoded
to download html without javascript processing, will not download
images, and respects robots.txt, which all provide good security.
'''

    def __init__(self,gb_per_month=gb_per_month,
                 max_links_cached=max_links_cached,
                 max_links_per_page=max_links_per_page,
                 max_links_per_domain=max_links_per_domain,
                 user_agent=user_agent,
                 search_url=search_url,
                 blacklist_url=blacklist_url,
                 wordsite_url=wordsite_url,
                 debug=False):
        self.gb_per_month = gb_per_month
        self.max_links_cached = max_links_cached
        self.max_links_per_page = max_links_per_page
        self.max_links_per_domain = max_links_per_domain
        self.user_agent = user_agent
        self.search_url = search_url
        self.blacklist_url = blacklist_url
        self.wordsite_url = wordsite_url
        self.debug = debug
        signal.signal(signal.SIGALRM, self.phantomjs_hang_handler) # register hang handler
        self.fake = Factory.create()
        self.hour_trigger = True
        self.twentyfour_hour_trigger = True
        self.links = set()
        self.link_count = dict()
        self.start_time = time.time()
        self.data_usage = 0
        self.get_blacklist()
        self.get_random_words()
        self.pollute_forever()

    def open_session(self):
        if not hasattr(self, 'session') or not isinstance(self.session, requests.sessions.Session):
            # requests session-based code
            # self.session = requests.Session()
            # self.session.headers.update({'User-Agent': self.user_agent})
            # use phantomjs
            # http://engineering.shapesecurity.com/2015/01/detecting-phantomjs-based-visitors.html
            # https://coderwall.com/p/9jgaeq/set-phantomjs-user-agent-string
            # http://phantomjs.org/api/webpage/property/settings.html
            dcap = dict(DesiredCapabilities.PHANTOMJS)
            # dcap['browserName'] = 'Chrome'
            dcap['phantomjs.page.settings.userAgent'] = ( self.user_agent )
            dcap['phantomjs.page.settings.loadImages'] = ( 'false' )
            dcap['phantomjs.page.customHeaders'] = ( { 'Connection': 'keep-alive', 'Accept-Encoding': 'gzip, deflate, sdch' } )
            driver = webdriver.PhantomJS(desired_capabilities=dcap,service_args=['--ignore-ssl-errors=true','--ssl-protocol=any'])
            driver.set_window_size(1296,1018)   #Tor browser size on Linux
            driver.implicitly_wait(30)
            driver.set_page_load_timeout(30)
            self.session = driver

    def quit_session(self):
        # self.session.close()  # quit closes all windows
        self.session.quit()
        del self.session

    def get_blacklist(self):
        self.blacklist_domains = set()
        self.blacklist_urls = set()
        try:
            if True:    # download the blacklist or not
                print('Downloading the blacklist...')
            else:
                raise Exception('Skip downloading the blacklist.')
            # http://stackoverflow.com/questions/18623842/read-contents-tarfile-into-python-seeking-backwards-is-not-allowed
            tgzstream = urllib.request.urlopen(urllib.request.Request(self.blacklist_url, headers={'User-Agent': self.user_agent}))
            tmpfile = BytesIO()
            while True:
                s = tgzstream.read(16384)
                if not s: break
                tmpfile.write(s)
            tgzstream.close()
            tmpfile.seek(0)
            tgz = tarfile.open(fileobj=tmpfile, mode='r:gz')
            # bash$ ls BL
            # COPYRIGHT	education	isp		recreation	updatesites
            # adv		finance		jobsearch	redirector	urlshortener
            # aggressive	fortunetelling	library		religion	violence
            # alcohol		forum		military	remotecontrol	warez
            # anonvpn		gamble		models		ringtones	weapons
            # automobile	global_usage	movies		science		webmail
            # chat		government	music		searchengines	webphone
            # costtraps	hacking		news		sex		webradio
            # dating		hobby		podcasts	shopping	webtv
            # downloads	homestyle	politics	socialnet
            # drugs		hospitals	porn		spyware
            # dynamic		imagehosting	radiotv		tracker
            for member in [ 'downloads', 'drugs', 'hacking', 'gamble', 'porn', 'spyware', 'updatesites', 'urlshortener', 'violence', 'warez', 'weapons' ]:
                self.blacklist_domains |= set(tgz.extractfile('BL/{}/domains'.format(member)).read().decode('utf-8').splitlines())
                self.blacklist_urls |= set(tgz.extractfile('BL/{}/urls'.format(member)).read().decode('utf-8').splitlines())
            tgz.close()
            tmpfile.close()
            print('done.')
        except BaseException as e:
            print(e)
        # ignore reductive subgraphs too
        self.blacklist_domains |= { 'wikipedia.org', 'wiktionary.org', 'startpage.com', 'startmail.com', 'ixquick.com', 'ixquick-proxy.com' }  # wiki, startpage-specific
        # and observed problem urls
        self.blacklist_urls |= { 'about:blank' }

    def get_random_words(self):
        try:
            reqsession = requests.Session()
            reqsession.headers.update({'User-Agent': self.user_agent})
            response = reqsession.get(self.wordsite_url,timeout=10)
            self.words = response.content.decode('utf-8').splitlines()
            reqsession.close()
        except BaseException as e:
            print(e)
            self.words = [ 'FUBAR' ]
        # if self.debug: print('There are {:d} words.'.format(len(self.words)))

    def pollute_forever(self):
        self.open_session()
        self.seed_links()
        self.quit_session()
        while True: # pollute forever, pausing only to meet the bandwidth requirement
            try:
                if self.diurnal_cycle_test():
                    self.open_session()
                    self.pollute()
                    self.quit_session()
                else:
                    time.sleep(self.chi2_mean_std(3.,1.))
                if npr.uniform() < 0.02: self.set_user_agent()  # reset the user agent occasionally
                self.elapsed_time = time.time() - self.start_time
                self.exceeded_bandwidth_tasks()
                self.every_hour_tasks()
                time.sleep(self.chi2_mean_std(0.5,0.2))
            except BaseException as e:
                print(e)

    def pollute(self):
        if len(self.links) < 2000: self.seed_links()
        url = self.remove_link()
        self.get_url(url)

    def seed_links(self):
        # initialize link-heavy, with ISP-oriented content
        self.links |= set( ['http://my.xfinity.com/news',
                           'http://my.xfinity.com/entertainment',
                           'http://my.xfinity.com/shopping',
                           'http://www.cnbc.com/',
                           'https://www.yahoo.com'] )
        if len(self.links) < self.max_links_cached:
            num_words = max(1,int(np.round(npr.poisson(1)+0.5)))  # mean of 1.5 words per search
            word = ' '.join(random.sample(self.words,num_words))
            if self.debug: print('Seeding with search for \'{}\'...'.format(word))
            # self.add_url_links(self.websearch(word).content.decode('utf-8'))
            self.get_websearch(word)

    def diurnal_cycle_test(self):
        now = dt.datetime.now()
        tmhr = now.hour + now.minute/60.
        phase = npr.normal(14.,1.)
        exponent = min(0.667,self.chi2_mean_std(0.333,0.1))
        def cospow(x,e):  # flattened cosine with e < 1
            c = np.cos(x)
            return np.sign(c) * np.power(np.abs(c), e)
        diurn = max(0.,0.5*(1.+cospow((tmhr-phase)*(2.*np.pi/24.),exponent)))
        flr = min(0.1,self.chi2_mean_std(0.02,0.002))
        val = flr + (1.-flr)*diurn
        return npr.uniform() < val

    def chi2_mean_std(self,mean=1.,std=0.1):
        '''
        Chi-squared random variable with given mean and standard deviation.
        '''
        scale = 2.*mean/std
        nu = mean*scale
        return npr.chisquare(nu)/scale

    def exceeded_bandwidth_tasks(self):
        if self.bandwidth_test():
            # decimate the stack and clear the cookies
            if len(self.links) > int(np.ceil(0.81*self.max_links_cached)):
                for url in random.sample(self.links,int(np.ceil(len(self.links)/10.))):
                    self.remove_link(url)
            time.sleep(120)

    def every_hour_tasks(self):
        if int(self.elapsed_time/60. % 60.) == 59:
            # reset user agent, clear out cookies
            if self.hour_trigger:
                self.set_user_agent()
                if hasattr(self,'session'):
                    # self.session.cookies.clear() # requests session
                    self.session.delete_all_cookies()
                self.hour_trigger = False
        else:
            self.hour_trigger = True
        self.every_day_tasks()
        self.every_two_weeks_tasks()

    def every_day_tasks(self):
        if int(self.elapsed_time/3600. % 24.) == 23:
            # clear out cookies every day, and seed more links
            if self.twentyfour_hour_trigger:
                if hasattr(self,'session'):
                    self.seed_links()
                    # restart the session
                    self.quit_session()
                    self.open_session()
                else:
                    self.open_session()
                    self.seed_links()
                    self.quit_session()
                self.twentyfour_hour_trigger = False
        else:
            self.twentyfour_hour_trigger = True

    def every_two_weeks_tasks(self):
        if self.elapsed_time > 3600.*24*14:
            # reset bw stats and (really) decimate the stack every couple of weeks
            self.start_time = time.time()
            self.data_usage = 0
            if len(self.links) > int(np.ceil(0.49*self.max_links_cached)):
                for url in random.sample(self.links,int(np.ceil(len(self.links)/3.))):
                    self.remove_link(url)

    def set_user_agent(self):
        global user_agent
        self.user_agent = self.fake.user_agent() if npr.random() < 0.95 else user_agent

    def remove_link(self):
        url = random.sample(self.links,1)[0];
        if npr.uniform() < 0.95:  # 95% 1 GET, ~5% 2 GETs, .2% three GETs
            self.links.remove(url)  # pop a random item from the stack
            self.decrement_link_count(url)
        return url

    def add_link(self,url):
        result = False
        domain = self.domain_name(url)
        self.link_count.setdefault(domain,0)
        if len(self.links) < self.max_links_cached \
                and self.link_count[domain] < self.max_links_per_domain \
                and url not in self.links:
            self.links.add(url)
            self.increment_link_count(url,domain)
            result = True
            # if self.debug: print('\tAdded link \'{}\'...'.format(url))
        return result

    def decrement_link_count(self,url,domain=None):
        if domain is None: domain = self.domain_name(url)
        self.link_count.setdefault(domain,0)
        if self.link_count[domain] > 0: self.link_count[domain] -= 1

    def increment_link_count(self,url,domain=None):
        if domain is None: domain = self.domain_name(url)
        self.link_count.setdefault(domain,0)
        self.link_count[domain] += 1

    def domain_name(self,url):
        return '.'.join(uprs.urlparse(url).netloc.split('.')[-2:])

    def get_websearch(self,query):
        '''HTTP GET of a websearch, then add any embedded links.'''
        url = uprs.urlunparse(uprs.urlparse(self.search_url)._replace(query='q={}'.format(query)))
        # return self.session.get(url)
        signal.alarm(20)  # set an alarm
        try:
            self.session.get(url)  # selenium driver
        except self.TimeoutError as e:
            print(e)
        finally:
            signal.alarm(0)  # cancel the alarm
        self.data_usage += len(self.session.page_source)
        new_links = self.websearch_links()
        if len(self.links) < self.max_links_cached: self.add_url_links(new_links)

    def websearch_links(self):
        '''Webpage format for a popular search engine, <div class="g">'''
        try:
            return [ div.find_element_by_tag_name('a').get_attribute('href') \
                for div in self.session.find_elements_by_css_selector('div.g') \
                     if div.find_element_by_tag_name('a').get_attribute('href') is not None ]
        except BaseException as e:
            print(e)
            return []

    def get_url(self,url):
        '''HTTP GET of the url, and add any embedded links.'''
        if not self.check_robots(url): return  # bail out if robots.txt says to
        signal.alarm(20)  # set an alarm
        try:
            self.session.get(url)  # selenium driver
        except self.TimeoutError as e:
            print(e)
        finally:
            signal.alarm(0)  # cancel the alarm
        self.data_usage += len(self.session.page_source)
        new_links = self.url_links()
        if len(self.links) < self.max_links_cached: self.add_url_links(new_links)

    def url_links(self):
        '''Generic webpage link finder format.'''
        try:
            return [ a.get_attribute('href') \
                     for a in self.session.find_elements_by_tag_name('a') \
                     if a.get_attribute('href') is not None ]
        except BaseException as e:
            print(e)
            return []

    def check_robots(self,url):
        result = False
        try:
            url_robots = uprs.urlunparse(uprs.urlparse(url)._replace(scheme='https',path='/robots.txt',query='',params=''))
            rp = RobotFileParserUserAgent()
            rp.set_url(url_robots)
            rp.read()
            result = rp.can_fetch(self.user_agent,url)
        except BaseException as e:
            print(e)
        del rp      # ensure self.close() in urllib
        return result

    def add_url_links(self,links):
        k = 0
        for link in sorted(links,key=lambda k: random.random()):
            lp = uprs.urlparse(link)
            if (lp.scheme == 'http' or lp.scheme == 'https') and not self.blacklisted(link):
                if self.add_link(link): k += 1
                if k > self.max_links_per_page: break
        if self.debug: print('Added {:d} links, {:d} total at url \'{}\'.'.format(k,len(self.links),self.session.current_url))

    def blacklisted(self,link):
        return link in self.blacklist_urls or self.domain_name(link) in self.blacklist_domains

    def bandwidth_test(self):
        running_bandwidth = self.data_usage/(self.elapsed_time+900.)
        running_bandwidth = running_bandwidth/407.	# Convert to GB/month, 2**30/(3600*24*30.5)
        # if self.debug: print('Using {} GB/month'.format(running_bandwidth))
        return running_bandwidth > self.gb_per_month

    # handle phantomjs timeouts
    class TimeoutError(Exception):
        pass

    def phantomjs_hang_handler(self, signum, frame):
        # https://github.com/detro/ghostdriver/issues/334
        # http://stackoverflow.com/questions/492519/timeout-on-a-function-call
        print('Looks like phantomjs has hung.')
        try:
            self.quit_session()
            self.open_session()
        except BaseException as e:
            print(e)
            raise self.TimeoutError('Unable to quit the session as well.')
        raise self.TimeoutError('phantomjs is taking too long')

    # original requests-based code fragments
    # def get_url(self,url):
    #     '''HTTP GET of the url, and add any embedded links.'''
    #     if self.check_size_and_set_mimetype(url) and self.mimetype == 'text/html':
    #         self.data_usage += self.content_length
    #         try:
    #             if self.check_robots(url):
    #                 response = self.session.get(url,allow_redirects=True,timeout=10)
    #                 if len(self.links) < self.max_links_cached: self.add_url_links(response.content.decode('utf-8'))
    #         except BaseException as e:
    #             print(e)

    # no HTTP HEAD support in phantomjs
    # def check_size_and_set_mimetype(self,url,maximum=1048576):
    #     '''Return True if not too large, set the mimetype as well.'''
    #     self.mimetype = None
    #     self.mimetype_options = None
    #     self.content_length = 0
    #     try:
    #         resp = self.session.head(url,allow_redirects=True,timeout=10)
    #         resp.raise_for_status()
    #         if 'Content-Type' in resp.headers:
    #             self.mimetype, self.mimetype_options = cgi.parse_header(resp.headers['Content-Type'])
    #         if 'Content-Length' in resp.headers:
    #             self.content_length = int(resp.headers['Content-Length'])
    #             if self.content_length > maximum:
    #                 raise Exception('Warning: Content size {:d} too large at url \'{}\'.'.format(int(resp.headers['Content-Length']),url))
    #     except BaseException as e:
    #         print(e)
    #         return False
    #     return True

if __name__ == "__main__":
    ISPDataPollution(debug=True)
