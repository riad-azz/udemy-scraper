import json
import os
import sqlite3
from datetime import datetime
from os import path, mkdir
from time import sleep

from requests import get

from assets.user_agent import get_ua


class Bot:
    CONFIG_DIR = "./config.json"
    DATABASE_DIR = "./database"
    LOGS_DIR = "./logs"

    def __init__(self):
        # --- Load configs ---
        if not path.exists(self.CONFIG_DIR):
            self.exit_error("Please add a config.json file then try again")
        with open(self.CONFIG_DIR, "r") as f:
            config_json = json.load(f)
        self.db_name = config_json.get("db_name", "database.db")
        self.keep_running = config_json.get("keep_running", False)
        self.keyword_pause = config_json.get("keyword_pause_time", 1)
        self.pause_time = config_json.get("finish_pause_time", 600)
        self.pages = config_json.get("pages", 5)
        # --- Load search preferences ---
        categories_file = "./categories.txt"
        keywords_file = "./keywords.txt"
        # load categories
        if not path.exists(categories_file):
            self.exit_error("Please add a categories.txt file then try again")
        with open(categories_file, "r") as f:
            temp_categories = f.read().strip()
            if temp_categories == "":
                self.exit_error("Please make sure to add the desired search configs to categories.txt")
            self.CATEGORIES = temp_categories.strip().split("\n")
        # load keywords
        if not path.exists(keywords_file):
            self.exit_error("Please add a keywords.txt file then try again")
        with open(keywords_file, "r") as f:
            temp_keywords = f.read().strip()
            if temp_keywords == "":
                self.exit_error("Please make sure to add the desired search configs to keywords.txt")
            self.KEYWORDS = temp_keywords.strip().split("\n")
        # --- Setup SQL ---
        self.connect = sqlite3.connect(f"{self.DATABASE_DIR}/{self.db_name}")
        self.cursor = self.connect.cursor()
        # Create courses table if it doesn't exist
        self.cursor.execute(
            "create table if not exists courses "
            "(COURSE_ID INTEGER ,CATEGORY_TITLE TEXT, COURSE_TITLE TEXT, "
            "URL TEXT, CREATED_TIME TEXT, PUBLISHED_TIME TEXT)")
        self.connect.commit()
        # --- APP VARS ---
        self.today = datetime.today()
        self.day = self.today.strftime("%Y-%m-%d")
        self.added_courses = self.load_courses()
        self.new_courses = 0
        self.total_new_courses = 0
        if not path.exists(self.LOGS_DIR):
            os.mkdir(self.LOGS_DIR)
        if path.exists(f"{self.LOGS_DIR}/log-{self.day}.txt"):
            with open(f"{self.LOGS_DIR}/log-{self.day}.txt", "r") as f:
                self.logs = f.readlines()
        else:
            self.logs = []

    def run(self):
        self.log_print("Starting bot...")
        while True:
            for keyword in self.KEYWORDS:
                self.log_print(f"Searching new courses for '{keyword}' for date : {self.day}")
                # Fetch all new courses
                all_courses = self.get_courses(keyword)
                if all_courses is None:
                    self.log_print(f"Couldn't find any search results for '{keyword}'")
                    continue

                # ID and CATEGORY of new courses
                courses = self.filter_courses(all_courses)

                # JSON course objects
                json_courses = self.get_courses_json(courses)

                # Save all courses to SQL
                self.save_all_courses(json_courses)

                # Report new courses found
                if self.new_courses > 0:
                    self.log_print(f"{self.new_courses} New '{keyword}' courses have been added")
                    self.total_new_courses += self.new_courses
                    self.new_courses = 0

                # pause to avoid getting banned
                sleep(self.keyword_pause)

            # Report how many new courses added
            self.log_print(f"{self.total_new_courses} total new courses has been added")
            self.total_new_courses = 0

            # Close bot if loop option is disabled
            if not self.keep_running:
                self.log_print("Bot is shutting down..")
                break

            # Pause to avoid being ip banned
            self.log_print(f"Pausing for {self.pause_time // 60} minutes")
            sleep(self.pause_time)
            self.log_print("Pause time finished. Bot Starting...")

    def log_print(self, msg):
        """
        Prints log msg and saves it to logs.txt file
        :param msg: str
        :return: None
        """
        self.save_log(msg)
        print(msg)

    def save_log(self, msg):
        curr_time = self.today.now().strftime("%H:%M:%S")
        line = f"{msg} - {curr_time} \n"
        self.logs.append(line)
        if not path.exists(self.LOGS_DIR):
            os.mkdir(self.LOGS_DIR)
        with open(f"{self.LOGS_DIR}/logs-{self.day}.txt", "w") as f:
            f.writelines(self.logs)

    def load_courses(self):
        """
        Returns a list of all the previously added courses to the SQL database
        :return: list[int]
        """
        column = self.cursor.execute("SELECT COURSE_ID FROM courses")
        courses_ids = [x[0] for x in list(column)]
        return courses_ids

    def get_courses(self, keyword):
        """
        Fetch courses using keyword from server side www.udemy.com
        :param keyword: str
        :return: list[dict]
        """
        courses_list = []
        for i in range(self.pages):
            curr_page = i + 1
            self.log_print(f"Fetching page {curr_page} for '{keyword}'")
            URL = f"https://www.udemy.com/api-2.0/search-courses/?p={curr_page}&q={keyword}" \
                  f"&sort=newest&src=ukw&skip_price=true&ordering=newest"
            HEADERS = {"authority": "www.udemy.com",
                       "User-Agent": get_ua(),
                       "referer": f"https://www.udemy.com/courses/search/?q={keyword}"}
            try:
                response = get(URL, headers=HEADERS, timeout=10)

                if response.status_code == 200:
                    courses = response.json()["courses"]
                    courses_list += courses
                else:
                    self.log_print(f"Failed to fetch page {curr_page} for '{keyword}'")
            except:
                self.log_print("connection problems please check your internet")

        if len(courses_list) >= 1:
            return courses_list

        return None

    def get_course_info(self, course_id):
        """
        Fetch course info with chosen fields from server side www.udemy.com
        :param course_id: int
        :return: dict (_class, course id, title, url, created, published_time) of requested course
        """
        URL = f"https://www.udemy.com/api-2.0/courses/{course_id}/?fields[course]=title,url,created,published_time"
        HEADERS = {"authority": "www.udemy.com",
                   "User-Agent": get_ua()}
        try:
            response = get(URL, headers=HEADERS, timeout=5)
            if response.status_code == 200:
                return response.json()
        except:
            self.log_print("connection problems please check your internet")

        return None

    def filter_courses(self, courses):
        """
        Filters the courses based on the date and the requested categories in categories.txt
        :param courses: list[dict]
        :return: dict (id, category)
        """
        filtered = []
        for course in courses:
            if len(course["badges"]) == 0:
                continue
            category = course["badges"][0]["context_info"]["category"]["title"]
            if category in self.CATEGORIES and course["id"] not in self.added_courses:
                course_obj = {"id": course["id"],
                              "category": category}
                filtered.append(course_obj)

        return filtered

    def get_courses_json(self, courses):
        """
        Create the required model with all required fields for the course to save in SQL
        :param courses: list[dict]
        :return: dict (_class, course id, category, title, url, created, published_time)
        """
        courses_json = []
        for course in courses:
            course_obj = self.get_course_info(course["id"])
            # Check if course was fetched
            if course_obj is None:
                self.log_print(f"Failed to fetch course info for course id : {course['id']}")
                continue
            # Check if was released today
            course_day = course_obj["published_time"][:10]
            if course_day != self.day:
                continue
            course_obj["category"] = course["category"]
            course_obj["url"] = "www.udemy.com" + course_obj["url"]
            courses_json.append(course_obj)

        return courses_json

    def save_course(self, course_obj):
        """
        Saves the course object in a SQL database
        :param course_obj: dict (_class, course id, category, title, url, created, published_time)
        :return: None
        """
        self.new_courses += 1
        course_id = course_obj["id"]
        category = course_obj["category"]
        title = course_obj["title"]
        url = course_obj["url"]
        created = course_obj["created"]
        published = course_obj["published_time"]
        self.cursor.execute(
            f"INSERT INTO courses('COURSE_ID' ,'CATEGORY_TITLE' , 'COURSE_TITLE' ,"
            f" 'URL' , 'CREATED_TIME' , 'PUBLISHED_TIME') "
            f"VALUES(?, ?, ?, ?, ?, ?)",
            (course_id, category, title, url, created, published))
        self.connect.commit()
        self.added_courses.append(course_id)

    def save_all_courses(self, courses):
        """
        Loop through all given courses and save them into a SQL database
        :param courses: list[dict]
        :return: None
        """
        for course in courses:
            self.save_course(course)

    @staticmethod
    def exit_error(msg):
        """
        Display error message then close the app on button press from user
        :param msg: str
        :return: None
        """
        print(msg)
        input("")
        quit()
