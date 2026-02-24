import pandas as pd
import sys

def verify_data():
    try:
        xls = pd.ExcelFile('Universities_and_Courses.xlsx')
        assert 'Universities' in xls.sheet_names, "Missing Universities sheet"
        assert 'Courses' in xls.sheet_names, "Missing Courses sheet"

        df_uni = pd.read_excel(xls, 'Universities')
        df_courses = pd.read_excel(xls, 'Courses')

        # Check unique IDs
        assert df_uni['university_id'].is_unique, "university_id is not unique"
        assert df_courses['course_id'].is_unique, "course_id is not unique"

        # Check no duplicates
        assert df_uni.duplicated().sum() == 0, "Duplicate entries in Universities"
        assert df_courses.duplicated().sum() == 0, "Duplicate entries in Courses"
        
        # Check required columns
        expected_uni_cols = ['university_id', 'university_name', 'country', 'city', 'website']
        assert all(col in df_uni.columns for col in expected_uni_cols), "Missing col in Universities"

        expected_course_cols = ['course_id', 'university_id', 'course_name', 'level', 'discipline', 'duration', 'fees', 'eligibility']
        assert all(col in df_courses.columns for col in expected_course_cols), "Missing col in Courses"

        # Check relational integrity
        valid_uni_ids = set(df_uni['university_id'])
        invalid_relations = df_courses[~df_courses['university_id'].isin(valid_uni_ids)]
        assert len(invalid_relations) == 0, "Relational integrity failed in Courses"

        print("All data verification checks passed successfully!")
    
    except Exception as e:
        print(f"Verification Failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    verify_data()
