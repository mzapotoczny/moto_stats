# -*- coding: UTF-8 -*-
import sys
import os
import re
import urllib
import logging
import hashlib
import dateutil
import traceback
from bs4 import BeautifulSoup

logging.basicConfig()
logger = logging.getLogger("OLX")
logger.setLevel(logging.INFO)

BS4_PARSER='lxml'

class olxChecker(object):
    searchUrl = 'http://olx.pl/'#motoryzacja/motocykle-skutery/?q=er-5'
    offerUrl = 'http://olx.pl/oferta/%s.html'
    offerPreg = None
    months = [u"stycznia", u"lutego", u"marca", u"kwietnia", u"maja", u"czerwca", u"lipca", u"sierpnia", u"września", u"października", u"listopada", u"grudnia"]

    
    def __init__(self, search_path):
        self.searchUrl += search_path
        self.offerPreg = re.compile('https?://(.+)/oferta/(.+).html.*$')
    
    def getPagedSearchUrl(self, page):
        if '?' in self.searchUrl:
            return self.searchUrl + '&page=' + str(page)
        else:
            return self.searchUrl + '?page=' + str(page)

    def getAnnoucementsForPage(self, page):
        code = BeautifulSoup(self.getCode(self.getPagedSearchUrl(page)), BS4_PARSER)
        links = code.find('table', attrs={'id':'offers_table'} )
        offers = [ x['href'] for x in links.find_all('a', attrs={'class': 'thumb'}) ]
        return offers
    
    def getPagesCount(self):
        code = BeautifulSoup(self.getCode(self.searchUrl), BS4_PARSER)
        return len(code.find('div', attrs={'class':'pager'}).find_all('span', attrs={'class':'item'}))

    def getAllOffers(self):
        pagesCount = self.getPagesCount()
        logger.info("Found %d pages" % (pagesCount))
        offers = []
        for page in xrange(1, pagesCount+1):
            page_offers = self.getAnnoucementsForPage(page)
            logger.info("Added %d offers from page %d" % (len(page_offers), page))
            offers += page_offers
        
        return [(lambda x: (x.group(1), x.group(2)))(self.offerPreg.search(offer))
                           for offer in offers]

    def removeSpaces(self, string):
        return " ".join( string.split() )
    
    def getOfferPhotosHash(self, offer):
        ourl = self.offerUrl % (offer)
        
        orig_code = self.getCode(ourl)
        code = BeautifulSoup(orig_code, BS4_PARSER)
        
        images = map((lambda x: x['src']), code.find('div', attrs={'class':'offercontentinner'}).find_all('img', attrs={'class':'bigImage'}))
        
        images = list(set(images))
        photos_hash = []
        for i, img in enumerate(images):
            logger.info("Downloading image {} ({}/{})".format(img,i+1,len(images)))
            try:
                f = urllib.urlopen(img) 
                data = f.read()
                photos_hash += [hashlib.sha256(data).digest()]
            except:
                logger.debug("Download of image {} failed".format(img))
            finally:
                f.close()
        return photos_hash

    def getOfferDetail(self, offer):
        ourl = self.offerUrl % (offer)
        
        orig_code = self.getCode(ourl)
        code = BeautifulSoup(orig_code, BS4_PARSER)
        
        images = map((lambda x: x['src']), code.find('div', attrs={'class':'offercontentinner'}).find_all('img', attrs={'class':'bigImage'}))
        
        images = list(set(images))
        
        try:
            photos_hash = []
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
                    details[name.getText().strip()] = val.find("strong").getText().strip()

            return {
                    "name": title.encode('ascii', 'ignore'),
                    "price": price,
                    "address":adress,
                    "data": data,
                    "details": details,
                    }
        except:
            logger.debug("Cannot analyze {}. Traceback:{}".format(offer, traceback.format_exc()))
            return {}

    def getCode(self, page):
        return urllib.urlopen(page).read()
