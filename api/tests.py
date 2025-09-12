from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APITestCase

from scraper.models import Job, RawJobPosting, ScrapingSession, JobMapping


class JobAPITests(APITestCase):
    """
    Comprehensive test suite for the Job Scraper API.
    """

    @classmethod
    def setUpTestData(cls):
        """
        Set up a diverse set of data to test against.
        This method is run once before all tests in this class.
        """
        # Create companies
        company_google = "Google"
        company_meta = "Meta"
        company_techsys = "Tech Systems Inc."

        # Create recent jobs for filtering
        cls.job1 = Job.objects.create(
            title="Senior Python Developer",
            company=company_google,
            location="New York, NY",
            description="Develop backend services using Python and Django.",
            first_seen=timezone.now() - timedelta(days=1),
            last_seen=timezone.now() - timedelta(days=1)
        )
        cls.job2 = Job.objects.create(
            title="Frontend Developer (React)",
            company=company_google,
            location="Chicago, IL",
            description="Build beautiful UIs with React and TypeScript.",
            first_seen=timezone.now() - timedelta(days=2),
            last_seen=timezone.now() - timedelta(days=2)
        )
        cls.job3 = Job.objects.create(
            title="Data Scientist (Python)",
            company=company_meta,
            location="Remote",
            description="Analyze data with Python, Pandas, and Scikit-learn.",
            first_seen=timezone.now() - timedelta(days=5),
            last_seen=timezone.now() - timedelta(days=5)
        )

        # Create an older job to test date filters
        cls.job4 = Job.objects.create(
            title="Project Manager",
            company=company_techsys,
            location="New York, NY",
            description="Manage project timelines and deliverables.",
            first_seen=timezone.now() - timedelta(days=30),
            last_seen=timezone.now() - timedelta(days=10)
        )

        # Create a successful scraping session for health check tests
        cls.session1 = ScrapingSession.objects.create(
            source_site='linkedin', status='completed', jobs_successful=10
        )

    def test_list_jobs_success_and_pagination(self):
        """Ensure the main jobs endpoint returns a 200 OK and is paginated."""
        url = reverse('api:job-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('results', response.data)
        self.assertEqual(response.data['count'], 4)

    def test_ranked_search_filter(self):
        """Test that the ranked search prioritizes title matches."""
        url = reverse('api:job-list')
        response = self.client.get(url, {'search': 'Python'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        
        # The first result should be the "Senior Python Developer" because it has a title match
        results = response.data['results']
        self.assertEqual(results[0]['title'], "Senior Python Developer")
        self.assertEqual(results[1]['title'], "Data Scientist (Python)")

    def test_multi_company_filter(self):
        """Test the 'companies' filter with comma-separated values (OR logic)."""
        url = reverse('api:job-list')
        response = self.client.get(url, {'companies': 'Google,Meta'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)

    def test_skills_filter(self):
        """Test the 'skills' filter (AND logic)."""
        url = reverse('api:job-list')
        # This should only match job1, which has both Python and Django
        response = self.client.get(url, {'skills': 'python,django'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.job1.id)

    def test_date_filter(self):
        """Test the 'posted_within_days' filter."""
        url = reverse('api:job-list')
        # Should return the 3 recent jobs, excluding the one from 30 days ago
        response = self.client.get(url, {'posted_within_days': '10'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)

    def test_ordering_filter(self):
        """Test that the ordering filter works correctly."""
        url = reverse('api:' 'job-list')
        response = self.client.get(url, {'ordering': 'company'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Results should be ordered by company name alphabetically
        companies = [result['company'] for result in response.data['results']]
        self.assertEqual(companies, ['Google', 'Google', 'Meta', 'Tech Systems Inc.'])

    def test_semantic_location_url(self):
        """Test that the /locations/<name>/jobs/ URL works."""
        url = reverse('api:location-jobs', kwargs={'location_name': 'New-York'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2) # job1 and job4 are in New York

    def test_semantic_url_conflict_validation(self):
        """Test that providing conflicting filters returns a 400 Bad Request."""
        url = reverse('api:company-jobs', kwargs={'company_name': 'Google'})
        response = self.client.get(url, {'companies': 'Meta'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_job_detail_view(self):
        """Test that retrieving a single job works and contains extra data."""
        url = reverse('api:job-detail', kwargs={'pk': self.job1.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], "Senior Python Developer")
        # Test for the extra data added in the view's retrieve() method
        self.assertIn('related_raw_postings', response.data)

    def test_trends_view_serializes_correctly(self):
        """Test the fix for the 'Job is not JSON serializable' TypeError."""
        url = reverse('api:trends')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check that the newest_job is a dictionary (serialized), not a raw object
        newest_job = response.data['market_summary']['newest_job']
        self.assertIsInstance(newest_job, dict)
        self.assertEqual(newest_job['id'], self.job1.id)

    def test_health_check_serializes_correctly(self):
        """Test the fix for the 'ScrapingSession is not JSON serializable' TypeError."""
        url = reverse('api:health-check')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check that the last_successful session is a dictionary (serialized)
        last_session = response.data['site_health']['linkedin']['last_successful']
        self.assertIsInstance(last_session, dict)
        self.assertEqual(last_session['id'], self.session1.id)