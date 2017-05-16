# -*- coding: UTF-8 -*-
import sys
import os
import re
import urllib
import logging
import hashlib
import dateutil
import dateutil.parser
import traceback
import cPickle as pickle
from bs4 import BeautifulSoup

logging.basicConfig()
logger = logging.getLogger("OLX")
logger.setLevel(logging.INFO)

BS4_PARSER='lxml'

class olxChecker(object):
    baseSearchUrl = 'http://olx.pl/{}'#motoryzacja/motocykle-skutery/?q=er-5'
    offerUrl = 'http://olx.pl/oferta/{}.html'
    offerPreg = None
    months = [u"stycznia", u"lutego", u"marca", u"kwietnia", u"maja", u"czerwca", u"lipca", u"sierpnia", u"września", u"października", u"listopada", u"grudnia"]
    
    def __init__(self, search_path=None, database=None):
        if search_path is None == database is None:
            raise RuntimeException("Exactly one of the parameters {search_path, database} must by non-empty")
        if search_path is not None:
            self.searchUrl = self.baseSearchUrl.format(search_path) 
            self.offers = {}
        else:
            with open(database, 'r') as f:
                self.searchUrl, self.offers = pickle.load(f)
        self.offerPreg = re.compile('https?://(.+)/oferta/(.+).html.*$')
    
    def pagedSearchUrl(self, page):
        if '?' in self.searchUrl:
            return self.searchUrl + '&page=' + str(page)
        else:
            return self.searchUrl + '?page=' + str(page)

    def annoucementsForPage(self, page):
        code = BeautifulSoup(self.code(self.pagedSearchUrl(page)), BS4_PARSER)
        links = code.find('table', attrs={'id':'offers_table'})
        offers = [ x['href'] for x in links.find_all('a', attrs={'class': 'thumb'}) ]
        offers = [(lambda x: (x.group(1), x.group(2)))(self.offerPreg.search(offer))
                       for offer in offers]
        return offers
    
    def pagesCount(self):
        code = BeautifulSoup(self.code(self.searchUrl), BS4_PARSER)
        max_pnum = 0
        for link in code.find('div', attrs={'class':'pager'}).find_all('a'):
            pnum = link.find('span').string
            try:
                pnum = int(pnum)
                max_pnum = max(max_pnum, pnum)
            except:
                pass
        return max_pnum

    def updateDatabase(self):
        pagesCount = self.pagesCount()
        logger.info("Found %d pages" % (pagesCount))
        offers = []
        for page in xrange(1, pagesCount+1):
            page_offers = self.annoucementsForPage(page)
            olx_offers = [offer[1] for offer in page_offers if offer[0] == 'www.olx.pl']
            logger.info("There are {} offers ({} are not from olx) on page {}"
                    .format(len(page_offers),
                            len(page_offers) - len(olx_offers),
                            page))
            old_offers = [offer in self.offers for offer in olx_offers]
            if all(old_offers):
                logger.info("All offers from page {} are old, breaking.".format(page))
                break
            offers += [offer for i, offer in enumerate(olx_offers) if not old_offers[i]]

        self.updateOffers(offers)
        return self.offers

    def connectOffers(self, fst, snd):
        fst['old_prices'] = [snd['price']] + snd.get('old_prices', [])
        return fst

    def mean(self, data):
        if len(data) > 0:
            return sum(data)*1.0/len(data)
        else:
            return 0

    def updateOffers(self, offers):
        for i, offer in enumerate(offers):
            logger.info("Downloading details {}/{}".format(i+1, len(offers)))
            code = None
            detail = {}
            try:
                code,detail = self.offerDetail(offer)
            except:
                logger.info("Failed to download detail from offer {} (#{})".format(offer,i+1))
            if detail != {}:
                hsh = detail['photos_hashes']
                found = False
                for ofr in list(self.offers.keys()):
                    det = self.offers[ofr]
                    if self.mean([phs in det['photos_hashes'] for phs in hsh]) > 0.5: # more than half
                        logger.info("Offer {} and {} are the same, connecting"
                                .format(offer, ofr))
                        self.offers[ofr] = self.connectOffers(detail, det)
                        found = True
                        break
                if not found:
                    logger.info("Adding new offer {}".format(offer))
                    self.offers[offer] = detail

    def offerPhotosHash(self, offer=None, code=None):
        if offer is None == code is None:
            raise RuntimeException("Exactly one of the parameters {offer, code} must by non-empty")
        
        if code is None:
            ourl = self.offerUrl.format(offer)
            orig_code = self.code(ourl)
            code = BeautifulSoup(self.code(ourl), BS4_PARSER)
        
        photos_hash = []
        try:
            images = map((lambda x: x['src']), code.find('div', attrs={'class':'offercontentinner'}).find_all('img', attrs={'class':'bigImage'}))
            images = list(set(images))
        except:
            images = []
        logger.debug("{} images".format(len(images)))
        for i, img in enumerate(images):
            try:
                f = urllib.urlopen(img) 
                data = f.read()
                photos_hash += [hashlib.sha256(data).digest()]
            except:
                logger.debug("Download of image {} failed".format(img))
            finally:
                f.close()
        return photos_hash

    def offerDetail(self, offer):
        ourl = self.offerUrl.format(offer)
        code = BeautifulSoup(self.code(ourl), BS4_PARSER)
        
        fb_title = code.findAll("meta", {"property":"og:title"})
        if len(fb_title) > 1:
            title = fb_title[1]['content']
        else:
            title = fb_title[0]['content']

        price = code.find("div", {"class":"pricelabel"}).find("strong").string
        price = price.replace(" ", "")
        price = price[:len(price)-2]
        price = int(price)
        adress = code.find("address").find("p").string.lstrip()

        data_raw = code.find(text=re.compile("Dodane o"))
        if data_raw == None:
            data_raw = code.find(text=re.compile("Dodane z telefonu"))
            data_raw = self.removeSpaces(data_raw.parent.parent.text)[27:]
            data_raw = data_raw[:data_raw.find(',')]
            data = data_raw
        else:
            data = (self.removeSpaces(data_raw)[16:]).encode('utf-8')
            data = data[:len(data)-1]
            
        for i in range(0, len(self.months)):
            if data.find(self.months[i]) != -1:
                data = data.lower().replace(" "+self.months[i]+" ", "."+str(i+1)+".")
                break
        
        data = dateutil.parser.parse(data, dayfirst = True)
        
        details = {}
        for val in code.find("table", {"class":"details"}).findAll("td"):
            name = val.find("th")
            if name:
                details[name.text.strip()] = val.find("strong").text.strip()

        return code, {
                "name": title.encode('ascii', 'ignore'),
                "price": price,
                "address":adress,
                "data": data,
                "details": details,
                "photos_hashes":self.offerPhotosHash(code=code)
                }

    def code(self, page):
        return urllib.urlopen(page).read()

    def save(self, filename):
        with open(filename, 'w') as f:
            pickle.dump((self.searchUrl, self.offers), f) 

    def removeSpaces(self, string):
        return " ".join( string.split() )
    
