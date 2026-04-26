"""
Tests for LABO API
Run with: pytest
"""

import pytest
from app import create_app


@pytest.fixture
def app():
    """Create app for testing"""
    app = create_app(config_name="testing")
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


class TestHealth:
    """Health check endpoints"""
    
    def test_health_check(self, client):
        response = client.get('/api/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert 'service' in data


class TestOverview:
    """Market overview endpoints"""
    
    def test_overview(self, client):
        response = client.get('/api/overview')
        assert response.status_code == 200
        data = response.get_json()
        
        # Check required fields
        assert 'total_jobs' in data
        assert 'total_organizations' in data
        assert 'avg_salary' in data
        assert 'remote_percentage' in data
        assert 'unique_skills' in data
        assert 'new_this_week' in data
        
        # Check data types
        assert isinstance(data['total_jobs'], int)
        assert isinstance(data['avg_salary'], dict)
        assert isinstance(data['remote_percentage'], float)


class TestJobs:
    """Job endpoints"""
    
    def test_recent_jobs_default(self, client):
        response = client.get('/api/jobs/recent')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
    
    def test_recent_jobs_with_limit(self, client):
        response = client.get('/api/jobs/recent?limit=5')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) <= 5
    
    def test_recent_jobs_with_keyword(self, client):
        response = client.get('/api/jobs/recent?keyword=engineer&limit=10')
        assert response.status_code == 200
        data = response.get_json()
        # Results should be relevant to keyword


class TestSkills:
    """Skill endpoints"""
    
    def test_top_skills(self, client):
        response = client.get('/api/skills/top')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        
        if data:
            skill = data[0]
            assert 'skill' in skill
            assert 'type' in skill
            assert 'count' in skill
            assert skill['type'] in ['knowledge', 'competence', 'skill']
    
    def test_top_skills_with_limit(self, client):
        response = client.get('/api/skills/top?limit=5')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) <= 5


class TestSalaries:
    """Salary endpoints"""
    
    def test_salaries_default(self, client):
        response = client.get('/api/salaries')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
    
    def test_salaries_by_department(self, client):
        response = client.get('/api/salaries?group_by=department')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
    
    def test_salaries_by_state(self, client):
        response = client.get('/api/salaries?group_by=state')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
    
    def test_salaries_by_grade(self, client):
        response = client.get('/api/salaries?group_by=grade')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
    
    def test_salaries_by_series(self, client):
        response = client.get('/api/salaries?group_by=series')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)


class TestLocations:
    """Location endpoints"""
    
    def test_locations(self, client):
        response = client.get('/api/locations')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        
        if data:
            location = data[0]
            assert 'location_state' in location
            assert 'count' in location
            assert 'avg_salary' in location
            assert 'remote_count' in location


class TestCategories:
    """Category endpoints"""
    
    def test_categories_summary(self, client):
        response = client.get('/api/categories/summary')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        
        if data:
            category = data[0]
            assert 'category' in category
            assert 'series_code' in category
            assert 'total_postings' in category
            assert 'avg_salary' in category
            assert 'remote_percentage' in category
    
    def test_collection_status(self, client):
        response = client.get('/api/categories/collection-status')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
