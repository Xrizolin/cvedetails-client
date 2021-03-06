#!/usr/bin/env python3
import re, logging, argparse
import grab

args_parser = argparse.ArgumentParser(
    description='Search cvedetails.com for CVEs by vendor, product and version, optionally by patch.',
    epilog='Multiword arguments should be in quotes')
args_parser.add_argument('vendor')
args_parser.add_argument('product')
args_parser.add_argument('version')
args_parser.add_argument('patch', default='', nargs='?')

logger = logging.getLogger(__name__)

search_url = "http://www.cvedetails.com/version-search.php?vendor={vendor}&product={product}&version={version}"

def get_references_from_cve_page(cve_id, cve_object=grab.Grab()):
    cve_url = "http://www.cvedetails.com/cve/" + cve_id
    cve_object.go(cve_url)
    references_table = cve_object.doc.select('//tr/td/a[@title="External url"]')
    return [reference.text() for reference in references_table]

def make_json_from_page(client):
    result_map = {}
    # result_map['CVES'] = []
    rows_in_table = len(client.g.doc.select('//table/tr')[12::2])
    # Описание полей и описание CVE идут отдельно строкой, поэтому шаг = 2
    # Вся магия основана на анализе html
    header = client.g.doc.select('//table/tr/th')[3:]
    for row_number in range(rows_in_table):
        row = client.g.doc.select('//table/tr/td')[9 + row_number * 16:]
        descr = client.g.doc.select('//table/tr/td')[24 + row_number * 16:]
        # В каждой строчке 16 полей, смещаемся каждый раз на 1 строку.
        row_map = {'Exploits': None}
        for i, field in enumerate(header):
            column_name = normalize_string(field.text())
            if column_name:
                row_map[column_name] = row[i].text()
        row_map['Text'] = descr[0].text()
        try:
            cve_id = row_map['CVEID']
            if cve_id:
                row_map['references'] = get_references_from_cve_page(cve_id)
        except:
            logger.warning("SOMETHING GONE WRONG")
            raise
        # result_map['CVES'].append(row_map['CVE ID']) Если понадобится список всех CVE отдельным листом
        result_map[cve_id] = row_map
    return result_map
    
def search_page(vendor, product, version, patch, client):
    rows_in_table = len(client.g.doc.select('//table[@class="searchresults"]/tr'))-1
    for row_number in range(rows_in_table):
        patch_from_html = client.g.doc.select('//table[@class="searchresults"]/tr/td')[5 + row_number * 9:][0]
        version_link_raw = client.g.doc.select('//table[@class="searchresults"]/tr/td')[8 + row_number * 9:][0].html()
        version_link = version_link_raw.split("\"")[5]
        if patch_from_html.text() == patch:
            try:
                patch_url = "http://www.cvedetails.com" + version_link
                client.g.go(patch_url)
                break
            except Exception as e:
                logging.critical('Cant fetch {0} with error {1}'.format(patch_url, e))
        else:
            logging.warning('Cant find match for {0}:{1}:{2}:{3}'.format(vendor, product, version, patch))

def vulns_page(client):
    html_with_pages_links = client.g.doc.select('//div[@class="paging"]/a')
    pages_links = [link.html().split(" ")[1] for link in html_with_pages_links]
    for page in pages_links:
        try:
            # Здесь происходить что-то странное
            client.g.go(page)
        except Exception as e:
            logging.warning('Cant fetch {0} with error {1}'.format(page, e))


class CVEDetailsClient:
    def __init__(self):
        self.g = grab.Grab(timeout=5, connect_timeout=5, user_agent='METASCAN')
        
############################# Дальше функции протестированы ####################
        
def normalize_string(string):
    return re.sub(r'[^a-zA-Z0-9]', '', string)

def determine_page_type(url, client):
    logger.info(url)
    try:
        client.g.go(url)
    except grab.error.GrabCouldNotResolveHostError as e:
        logger.critical('Cant fetch {0} with error {1}'.format(url, e))
        raise e
    table_header = client.g.doc.select('//td/div/h1').text()
    error = client.g.doc.text_search(u'No matches')
    if error:
        return "error"
    elif table_header == "Vendor, Product and Version Search":
        return "search_page"
    elif "Vulnerabilities" in table_header:
        return "vulns_page"
    else:
        return "error"

def main(vendor, product, version, patch='', client=CVEDetailsClient()):
    page_type = determine_page_type(search_url.format(vendor=vendor, product=product, version=version), client=client)
    logger.info(page_type)
    if page_type == 'search_page':
        search_page(vendor, product, version, patch, client=client)
        return make_json_from_page(client)
    elif page_type == 'vulns_page':
        vulns_page(client=client)
        return make_json_from_page(client)
    return {}
    

if __name__ == '__main__':
    args = args_parser.parse_args()
    result = main(**vars(args))
    for _, v in result.items():
        print("{CVEID} TYPE: {VulnerabilityTypes}, SCORE: {Score}, PUBLISHED: {PublishDate} \nEXPLOITS: {Exploits}\n{Text} \n".format(**v))
