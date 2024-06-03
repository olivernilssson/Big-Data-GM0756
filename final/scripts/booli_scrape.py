# Import required libraries
import re
import pandas as pd
import requests as req
import bs4
import time

# Define function for extracting the data


def total_floors(address):
    base_address = 'https://www.allabrf.se/'
    building_address = address.lower().replace(' ', '-').replace('å', 'a').replace('ä', 'a').replace('ö', 'o').replace('é', 'e')
    start_address = base_address + building_address
    print(f"Scraping address: {start_address}")
    try:
        response = req.get(start_address)
        time.sleep(2)
        response.raise_for_status()
        print(f"Response code: {response.status_code} - Request OK")
    except (req.exceptions.HTTPError, req.exceptions.RequestException) as err:
        print(err)
        return None

    soup = bs4.BeautifulSoup(response.text, 'lxml')
    div = soup.find('div', {'class': 'component--apartments'})
    if div:
        table = div.find('tbody')
        if table:
            rows = table.find_all('tr')
            last_vaning = None
            for row in rows:
                tds = row.find_all('td')
                if 'Våning' in tds[0].text:
                    match = re.search(r'\d+', tds[0].text)
                    if match:
                        last_vaning = int(match.group())
                        if 'Gatuplan' in rows[0].text:
                            last_vaning += 1
            print(f"Number of floors: {last_vaning}")
            return last_vaning
    else:
        print("No table found")
        return None


def get_object_page(soup):
    objs = soup.find_all('li', {'class': 'search-page__module-container'})
    apartments = []

    for obj in objs:
        div1 = obj.find('div', {'class': 'absolute flex flex-col h-full w-full items-center justify-center'})
        div2 = obj.find('div', {'class': 'object-card__content sm:pb-3'})
        if div1 and div2:
            try:
                price_change = list(div1.find('div', {'class': 'text-md font-medium mt-1'}).stripped_strings)[0]
            except AttributeError:
                price_change = '0%'
            text_elements = list(div2.stripped_strings)
            combined_elements = text_elements + [price_change]
            apartment = {
                'date': None,
                'address': None,
                'city': None,
                'rooms': None,
                'area': None,
                'floor': None,
                'total_floors': None,
                'top_floor': None,
                'elevator': None,
                'balcony': None,
                'sell_price': None,
                'ask_price': None,
                'price_change': None,
                'price_per_m2': None,
                'interest_rate': None
            }
            # Loop through the text elements and extract the relevant information with error handling to prevent crashes
            for element in combined_elements:
                if 'vån\xa0' in element:
                    try:
                        apartment['floor'] = int(element.lstrip('vån\xa0'))
                    except ValueError:
                        apartment['floor'] = None
                elif 'kr' in element:
                    try:
                        apartment['sell_price'] = int(element.replace('\xa0', '').strip('kr').replace(' ', ''))
                        if price_change != '0%':
                            apartment['price_change'] = float(combined_elements[-1].replace(',', '.').strip('% +-/'))
                        else:
                            apartment['price_change'] = 0
                        apartment['ask_price'] = round((apartment['sell_price'] / (1 + apartment['price_change'] / 100)))
                    except ValueError:
                        apartment['sell_price'] = None
                elif 'm²' in element:
                    try:
                        area = element.replace('m²', '').replace('\xa0m²', '').strip()
                        apartment['area'] = float(area.replace('½', '')) + 0.5 if '½' in element else float(area)
                        apartment['price_per_m2'] = round(apartment['sell_price'] / apartment['area'], 2)
                    except ValueError:
                        apartment['area'] = None
                elif '\xa0rum' in element:
                    try:
                        rooms = element.replace('½', '').rstrip('\xa0rum').strip()
                        apartment['rooms'] = float(rooms) + 0.5 if '½' in element else float(rooms)
                    except ValueError:
                        apartment['rooms'] = None
            # Address and date are the first two elements assumed by their order
            apartment['address'] = text_elements[0] if len(text_elements) > 0 else None
            apartment['date'] = text_elements[1] if len(text_elements) > 1 else None
            apartment['city'] = text_elements[2].split('·')[-1].strip() if len(text_elements) > 2 else None
            total_floors_value = total_floors(apartment['address'])
            if apartment['floor'] is not None and total_floors_value is not None:
                apartment['total_floors'] = max(apartment['floor'], total_floors_value)
                apartment['top_floor'] = int(apartment['floor'] == total_floors_value)
            # Check if the apartment is in the list of elevator apartments and set the elevator value
            if not elevator_apartments.empty:
                elevator_apartment = elevator_apartments[(elevator_apartments['address'] == apartment['address'])
                                                         & (elevator_apartments['rooms'] == apartment['rooms'])]
                if not elevator_apartment.empty:
                    apartment['elevator'] = 1
                else:
                    apartment['elevator'] = 0
            # Check if the apartment is in the list of balcony apartments and set the elevator value
            if not balcony_apartments.empty:
                balcony_apartment = balcony_apartments[(balcony_apartments['address'] == apartment['address'])
                                                       & (balcony_apartments['rooms'] == apartment['rooms'])]
                if not balcony_apartment.empty:
                    apartment['balcony'] = 1
                else:
                    apartment['balcony'] = 0
            # Add interest rate to each apartments sell date. Date is in first column named "Datum" and the interest rate in the second column. Date is only updated once per quarter.
            if interest_riksbanken is not None:
                interest_rate = interest_riksbanken[interest_riksbanken['date'] <= apartment['date']]
                if not interest_rate.empty:
                    apartment['interest_rate'] = interest_rate.loc[interest_rate.index[-1], 'rate']
            apartments.append(apartment)  # Append the apartment to the list of apartments
    return apartments  # Return the list of apartments to the function caller


def get_all_objects(end_url):
    base_address = 'https://www.booli.se/'
    start_address = base_address + end_url  # Create the start address

    # Test response, should return 200 if request was OK
    # Use try-except to catch any errors and prevent the script from crashing
    try:
        response = req.get(start_address)
        response.raise_for_status()
        print(f"Response code: {response.status_code} - Request OK")
    except req.exceptions.HTTPError as err:
        print(err)
        return None

    # Parse the response with BeautifulSoup
    soup = bs4.BeautifulSoup(response.text, 'lxml')
    apartments = pd.DataFrame(get_object_page(soup))  # Create a DataFrame from the list of apartments

    page = 0  # Initialize the page counter
    while True:
        # If the next page link is found, update the soup and continue the loop
        next_page = [x for x in soup.find_all('a') if x.string == 'Nästa sida']  # Find the next page link
        page += 1
        print(f"Scraping page {page}")
        if next_page:
            next_page = base_address + next_page[0]['href']
            response = req.get(next_page)
            soup = bs4.BeautifulSoup(response.text, 'lxml')
            apartments = pd.concat([apartments, pd.DataFrame(get_object_page(soup))], ignore_index=True)
        else:
            break
        time.sleep(2.5)  # Sleep for 2.5 seconds to avoid overloading the server

    # Save the DataFrame to a CSV file
    apartments.dropna(inplace=True)  # Drop rows with missing values
    apartments.to_csv('final/data/booli_apartments.csv', index=False)
    return apartments  # Return the DataFrame to the function caller


def get_object_page_light(soup):
    objs = soup.find_all('li', {'class': 'search-page__module-container'})
    apartments = []

    for obj in objs:
        div = obj.find('div', {'class': 'object-card__content sm:pb-3'})
        if div:
            text_elements = list(div.stripped_strings)
            apartment = {
                'date': None,
                'address': None,
                'rooms': None,
                'area': None,
                'floor': None,
                'sell_price': None,
                'price_per_m2': None
            }
            # Loop through the text elements and extract the relevant information with error handling to prevent crashes
            for element in text_elements:
                if 'vån\xa0' in element:
                    try:
                        apartment['floor'] = int(element.lstrip('vån\xa0'))
                    except ValueError:
                        apartment['floor'] = None
                elif 'kr' in element:
                    try:
                        apartment['sell_price'] = int(element.replace('\xa0', '').strip('kr').replace(' ', ''))
                    except ValueError:
                        apartment['sell_price'] = None
                elif 'm²' in element:
                    try:
                        area = element.replace('m²', '').replace('\xa0m²', '').strip()
                        apartment['area'] = float(area.replace('½', '')) + 0.5 if '½' in element else float(area)
                        apartment['price_per_m2'] = apartment['sell_price'] / apartment['area']
                    except ValueError:
                        apartment
                elif '\xa0rum' in element:
                    try:
                        rooms = element.replace('½', '').rstrip('\xa0rum').strip()
                        apartment['rooms'] = float(rooms) + 0.5 if '½' in element else float(rooms)
                    except ValueError:
                        apartment['rooms'] = None
            # Address and date are the first two elements assumed by their order
            apartment['address'] = text_elements[0] if len(text_elements) > 0 else None
            apartment['date'] = text_elements[1] if len(text_elements) > 1 else None
            apartments.append(apartment)  # Append the apartment to the list of apartments
    return apartments  # Return the list of apartments to the function caller


def get_all_objects_filter(end_url, file_name):
    base_address = 'https://www.booli.se/'
    start_address = base_address + end_url  # Create the start address

    # Test response, should return 200 if request was OK
    # Use try-except to catch any errors and prevent the script from crashing
    try:
        response = req.get(start_address)
        response.raise_for_status()
        print(f"Response code: {response.status_code} - Request OK")
    except req.exceptions.HTTPError as err:
        print(err)
        return None

    # Parse the response with BeautifulSoup
    soup = bs4.BeautifulSoup(response.text, 'lxml')
    apartments = pd.DataFrame(get_object_page_light(soup))  # Create a DataFrame from the list of apartments

    page = 0  # Initialize the page counter
    while True:
        # If the next page link is found, update the soup and continue the loop
        next_page = [x for x in soup.find_all('a') if x.string == 'Nästa sida']  # Find the next page link
        page += 1
        print(f"Scraping page {page}")
        if next_page:
            next_page = base_address + next_page[0]['href']
            response = req.get(next_page)
            soup = bs4.BeautifulSoup(response.text, 'lxml')
            apartments = pd.concat([apartments, pd.DataFrame(get_object_page_light(soup))], ignore_index=True)
        else:
            break
        time.sleep(2)  # Sleep for 2 seconds to avoid overloading the server

    # Save the DataFrame to a CSV file
    apartments.dropna(inplace=True)  # Drop rows with missing values
    apartments.to_csv(f'final/data/{file_name}.csv', index=False)
    return apartments  # Return the DataFrame to the function caller


max_sold_date = '2024-05-20'
min_sold_date = '2024-01-01'

# Read xlsx file with interest rates from Riksbanken
interest_riksbanken = pd.read_excel('final/data/styrrantan-effektiv.xlsx', sheet_name='Reporäntan per förändring')
# Rename columns to date and rate
interest_riksbanken.columns = ['date', 'rate']

elevator_apartments = get_all_objects_filter(
    f'sok/slutpriser?areaIds=115329&amenities=buildingHasElevator&maxSoldDate={max_sold_date}&minSoldDate={min_sold_date}&rooms=2,1',
    'elevator_apartments')

balcony_apartments = get_all_objects_filter(
    f'sok/slutpriser?areaIds=115329&amenities=hasBalconyOrPatio&maxSoldDate={max_sold_date}&minSoldDate={min_sold_date}&rooms=2,1',
    'balcony_apartments')

get_all_objects(f'sok/slutpriser?areaIds=115329&maxSoldDate={max_sold_date}&minSoldDate={min_sold_date}&rooms=2,1')
