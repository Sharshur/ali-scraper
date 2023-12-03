import csv
import re
import os
import random
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common import exceptions
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService


class CurrencyNotInShekelException(Exception):
    pass


class RegexMatchError(Exception):
    pass


# Runs raw_price through regex format to extract only numbers after ₪ and before . - Throws custom errors
def extract_price(raw_price):
    pattern = r'₪(\d+)'
    match = re.search(pattern, raw_price)

    if not match:
        if raw_price[0] != '₪':
            raise CurrencyNotInShekelException
        else:
            raise RegexMatchError

    return match.group(1)


def read_last_line_from_csv(file_path):
    with open(file_path, mode='r', encoding='utf-8') as file:
        last_line = None
        for line in csv.reader(file):
            last_line = line
        return last_line


# Prompts user for run type ('new' or 'continue')
def discern_run_type():
    while True:
        choice = input("Is this a brand new run (enter 'new') or a subsequent run after a stop or error (enter 'continue')? ").strip().lower()
        if choice in ('new', 'continue'):
            return choice


def main():
    # Assign file path variables
    input_file = 'all_products.csv'
    output_file = 'all_products_output.csv'
    no_price_log_file = 'no_price_log.csv'

    # Set options for webdriver
    options = webdriver.ChromeOptions()
    # Uncomment the following line to run Chrome in headless mode
    # options.add_argument("--headless=new")
    options.add_argument("--lang=he")  # Set language to Hebrew
    options.add_argument("--force-country=IL")  # Set country to Israel

    # Variable for keeping track of CurrencyNotInShekelException exceptions and exit if there are 10 or more overall.
    currency_exceptions = 0

    # File verification processes, make sure all needed files exist.

    if not (os.path.exists(no_price_log_file)):
        with open(no_price_log_file, mode='w', encoding='utf-8'):
            print(f'No no price log file named {no_price_log_file} found, creating a blank one.')

    if not (os.path.exists(output_file)):
        with open(output_file, mode='w', encoding='utf-8'):
            print(f'No output file named {output_file} found, creating a blank one.')

    if not os.path.exists(input_file) or os.path.getsize(input_file) == 0:
        print(f'No valid product input file found, please make sure you have a non-empty products file named {input_file} in this directory.')
        exit()

    try:
        # Prompt user for run type and run program accordingly
        run_type = discern_run_type()

        # Open input and output files and assign csv reader and writer
        with open(input_file, mode='r', encoding='utf-8') as input_f, open(output_file, mode='a', newline='', encoding='utf-8') as output_f:
            csv_reader = csv.reader(input_f)
            csv_writer = csv.writer(output_f)

            header = next(csv_reader)

            # New: Truncate output file then add header to it        ALSO TRUNCATE NPL FILE FOR TESTING
            if run_type == 'new':
                with open(output_file, mode='w', encoding='utf-8'), open(no_price_log_file, mode='w', encoding='utf-8'):
                    csv_writer.writerow(header)
                    output_f.flush()

            # Continue: Verify there is product ID in the output file, if not warn user and exit
            else:  # run_type == 'continue'
                last_line = read_last_line_from_csv(output_file)
                last_product_id = last_line[0]
                print(f'Proceeding from Product ID {last_product_id}')
                if last_product_id:
                    for row in csv_reader:
                        if row[0] == last_product_id:
                            break
                else:
                    print(f'No previous product ID found in output file {output_file}, please verify you are using the correct option.')
                    exit()

            with webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options) as driver:
                for row in csv_reader:
                    while True:
                        try:
                            product_id = row[0]
                            url = row[3]

                            # If unpublished skip
                            if row[1] != '1':
                                print(f'ID {product_id}: Unpublished - skipping')
                                csv_writer.writerow(row)
                                output_f.flush()
                                break

                            driver.get(url)
                            time.sleep(random.uniform(2, 4))

                            raw_price_element = driver.find_element(By.CLASS_NAME, 'product-price-current')
                            raw_price = raw_price_element.text

                            # Run raw_price through regex format to extract only numbers after ₪ and before .
                            processed_price = extract_price(raw_price)

                            print(f'ID {product_id}: Updated price from {row[2]} to {processed_price}')
                            row[2] = processed_price

                        except exceptions.InvalidArgumentException:
                            print(f'ID {product_id}: No link in csv file, skipping')
                            # row[1] = -1  # Mark published status as 0 if no link found then proceed to write and flush row

                        except exceptions.NoSuchElementException:
                            try:  # check for uniform
                                raw_price_element = driver.find_element(By.CLASS_NAME, 'uniform-banner-box-price')
                                raw_price = raw_price_element.text
                                processed_price = extract_price(raw_price)
                                print(f'ID {product_id}: Updated price from {row[2]} to {processed_price}')
                                row[2] = processed_price

                            except exceptions.NoSuchElementException:
                                print(f'ID {product_id}: No price in link')
                                row[1] = -1  # Mark published status as 0 if no price found then proceed to write and flush row

                                # Log all no price found files for testing later
                                with open(no_price_log_file, mode='a', newline='', encoding='utf-8') as npl_f:
                                    csv.writer(npl_f).writerow(row)

                        except exceptions.NoSuchWindowException:
                            print('NoSuchWindowException occurred. Reopening the driver and continuing...')
                            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

                        except CurrencyNotInShekelException:
                            print(f'Currency not in shekel for product ID {product_id} - {raw_price}\nClosing and reopening driver then retrying...')
                            if currency_exceptions >= 10:
                                print(f'10 currency exceptions reached on product ID {product_id} - {raw_price}, please contact Roy Keinan 0509139898 - Exiting...')
                                exit()
                            # Close and reopen driver to fix currency and continue to keep trying the product
                            driver.close()
                            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
                            continue

                        except RegexMatchError:
                            print(f'Regex match error for product ID {product_id} - {raw_price}\nPlease contact Roy Keinan 0509139898\nExiting...')
                            exit()

                        except Exception as e:
                            print(f'Unrecognized error processing product ID {product_id}\nPlease contact Roy Keinan 0509139898\n{e}')
                            exit()

                        # Write row if all is well, flush to save in case of error (large dataset)
                        csv_writer.writerow(row)
                        output_f.flush()
                        break

    except KeyboardInterrupt:
        print('\nUser closed program preemptively, please do not try to force exit again - exiting...')
        exit()

    except Exception as gen_exc:
        print(f'General unknown exception - Please contact Roy Keinan 0509139898\n{gen_exc}')
        exit()

    print('Program finished successfully!')


if __name__ == '__main__':
    main()
