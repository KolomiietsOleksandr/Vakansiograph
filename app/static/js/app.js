/**
 * LABO Dashboard - JavaScript (API-Integrated Version)
 * Compatible with dashboard.html structure
 */

// ============================================================================
// CONFIGURATION & CONSTANTS
// ============================================================================

const chartColorsArray = [
  '#3498DB', '#E74C3C', '#2ECC71', '#F39C12', '#9B59B6',
  '#1ABC9C', '#06C6FF', '#E91E63', '#4A90E2', '#A4DE6C'
];

// Chart defaults
Chart.defaults.color = 'rgba(255, 255, 255, 0.6)';
Chart.defaults.borderColor = 'rgba(255, 107, 53, 0.1)';

const baseChartOptions = {
  maintainAspectRatio: false,
  responsive: true,
  plugins: {
    filler: { propagate: true },
    legend: {
      labels: {
        color: 'rgba(255, 255, 255, 0.8)',
        font: { size: 12, weight: '500', family: "'Outfit', sans-serif" },
        padding: 16,
        usePointStyle: true,
        pointStyle: 'circle'
      }
    }
  }
};

const baseScalesOptions = {
  x: {
    grid: {
      color: 'rgba(255, 107, 53, 0.08)',
      drawBorder: false,
      drawTicks: true
    },
    ticks: {
      color: 'rgba(255, 255, 255, 0.6)',
      font: { size: 11, weight: '500' }
    }
  },
  y: {
    grid: {
      color: 'rgba(255, 107, 53, 0.08)',
      drawBorder: false
    },
    ticks: {
      color: 'rgba(255, 255, 255, 0.6)',
      font: { size: 11, weight: '500' }
    },
    beginAtZero: true
  }
};

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

const CACHE_TTL = 10 * 60 * 1000; // 10 minutes

async function fetchAPI(endpoint) {
  const key = 'vkg_' + endpoint;
  try {
    const cached = localStorage.getItem(key);
    if (cached) {
      const { ts, data } = JSON.parse(cached);
      if (Date.now() - ts < CACHE_TTL) return data;
    }
  } catch (_) {}

  try {
    const response = await fetch(endpoint);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    try { localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data })); } catch (_) {}
    return data;
  } catch (error) {
    console.error(`API Error (${endpoint}):`, error);
    throw error;
  }
}

/**
 * Show error message in container
 */
function showError(containerId, message = 'Failed to load data') {
  const container = document.getElementById(containerId);
  if (container) {
    container.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 20px;">⚠️ ${message}</div>`;
  }
}

/**
 * Generate date labels for last N days
 */
function getDateLabels(days = 7) {
  const labels = [];
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    labels.push(date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
  }
  return labels;
}

// ============================================================================
// CHART RENDERING FUNCTIONS
// ============================================================================

/**
 * Render Overview Metrics (Dashboard cards)
 */
window.renderMetrics = async function() {
  const container = document.getElementById('metrics');
  if (!container) {
    console.warn('Metrics container not found');
    return;
  }

  try {
    const data = await fetchAPI('/api/overview');

    const metricsHTML = `
      <div class="card">
        <div class="stat-num">${data.total_jobs.toLocaleString()}</div>
        <div class="stat-label">Total Job Postings</div>
      </div>
      <div class="card">
        <div class="stat-num">${data.new_this_week.toLocaleString()}</div>
        <div class="stat-label">New This Week</div>
      </div>
      <div class="card">
        <div class="stat-num">${data.unique_skills.toLocaleString()}</div>
        <div class="stat-label">Unique Skills Found</div>
      </div>
      <div class="card">
        <div class="stat-num">${data.remote_percentage.toFixed(1)}%</div>
        <div class="stat-label">Telework Available</div>
      </div>
    `;

    container.innerHTML = metricsHTML;
  } catch (error) {
    console.error('Failed to render metrics:', error);
    showError('metrics');
  }
};

/**
 * Render Trend Chart
 */
window.renderTrendChart = async function() {
  const ctx = document.getElementById('trendChart');
  if (!ctx) return;

  try {
    const response = await fetchAPI('/api/categories/summary');
    const topCategories = response.categories.slice(0, 5);
    const labels = getDateLabels(7);

    const datasets = topCategories.map((cat, idx) => {
      const dailyCount = Math.floor(cat.total_postings / 7);
      return {
        label: cat.category,
        data: Array(7).fill(dailyCount),
        borderColor: chartColorsArray[idx],
        backgroundColor: chartColorsArray[idx] + '15',
        fill: true,
        tension: 0.4,
        borderWidth: 2.5,
        pointBorderColor: '#141820',
        clip: false
      };
    });

    if (window.trendChartInstance) {
      window.trendChartInstance.destroy();
    }

    window.trendChartInstance = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets },
      options: { ...baseChartOptions, scales: baseScalesOptions }
    });
  } catch (error) {
    console.error('Failed to render trend chart:', error);
  }
};

/**
 * Render Group Chart (Job Categories)
 */
window.renderGroupChart = async function() {
  const ctx = document.getElementById('groupChart');
  if (!ctx) return;

  try {
    const response = await fetchAPI('/api/categories/summary');
    const { categories, coverage } = response;
    const topCategories = categories.slice(0, 8);

    const coverageNote = document.getElementById('groupChartCoverage');
    if (coverageNote) {
      coverageNote.textContent = `Based on ${coverage.jobs_with_series.toLocaleString()} of ${coverage.total_jobs.toLocaleString()} jobs with OPM series code (${coverage.coverage_pct}%)`;
    }

    const data = {
      labels: topCategories.map(c => c.category),
      datasets: [{
        label: 'Job Postings',
        data: topCategories.map(c => c.total_postings),
        backgroundColor: chartColorsArray.slice(0, topCategories.length),
        borderColor: 'rgba(255, 107, 53, 0.3)',
        borderWidth: 1.5,
        borderRadius: 8,
        hoverBackgroundColor: 'rgba(255, 107, 53, 0.2)'
      }]
    };

    if (window.groupChartInstance) {
      window.groupChartInstance.destroy();
    }

    window.groupChartInstance = new Chart(ctx, {
      type: 'bar',
      data,
      options: {
        ...baseChartOptions,
        indexAxis: 'y',
        scales: {
          x: { ...baseScalesOptions.x, beginAtZero: true },
          y: { ...baseScalesOptions.y, grid: { display: false, drawBorder: false } }
        }
      }
    });
  } catch (error) {
    console.error('Failed to render group chart:', error);
  }
};

/**
 * Render Skill Type Distribution
 */
window.renderTypeChart = async function() {
  const ctx = document.getElementById('typeChart');
  if (!ctx) return;

  try {
    const skills = await fetchAPI('/api/skills/top?limit=100');
    
    const skillTypeCounts = { skill: 0, competence: 0, knowledge: 0 };
    skills.forEach(s => {
      if (skillTypeCounts.hasOwnProperty(s.type)) {
        skillTypeCounts[s.type]++;
      }
    });

    const data = {
      labels: ['Skill', 'Competence', 'Knowledge'],
      datasets: [{
        data: [skillTypeCounts.skill, skillTypeCounts.competence, skillTypeCounts.knowledge],
        backgroundColor: ['#9B59B6', '#2ECC71', '#3498DB'],
        borderColor: 'rgba(255, 107, 53, 0.2)',
        borderWidth: 2
      }]
    };

    if (window.typeChartInstance) {
      window.typeChartInstance.destroy();
    }

    window.typeChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data,
      options: {
        ...baseChartOptions,
        plugins: {
          ...baseChartOptions.plugins,
          legend: { ...baseChartOptions.plugins.legend, position: 'bottom' }
        }
      }
    });
  } catch (error) {
    console.error('Failed to render type chart:', error);
  }
};

/**
 * Render Radar Chart
 */
window.renderRadar = async function() {
  const ctx = document.getElementById('radarChart');
  if (!ctx) return;

  try {
    const response = await fetchAPI('/api/categories/summary');
    const topCategories = response.categories.slice(0, 8);
    const maxPostings = Math.max(...topCategories.map(c => c.total_postings));
    
    const currentData = topCategories.map(c => (c.total_postings / maxPostings) * 100);

    const data = {
      labels: topCategories.map(c => c.category),
      datasets: [
        {
          label: 'Job Postings (normalized)',
          data: currentData,
          borderColor: '#06C6FF',
          backgroundColor: 'rgba(6, 198, 255, 0.25)',
          borderWidth: 3,
          pointBackgroundColor: '#06C6FF',
          pointBorderColor: '#141820',
          pointBorderWidth: 3,
          pointRadius: 5,
          pointHoverRadius: 7,
          fill: true,
          tension: 0.2
        }
      ]
    };

    if (window.radarChartInstance) {
      window.radarChartInstance.destroy();
    }

    window.radarChartInstance = new Chart(ctx, {
      type: 'radar',
      data,
      options: {
        ...baseChartOptions,
        plugins: {
          ...baseChartOptions.plugins,
          legend: {
            ...baseChartOptions.plugins.legend,
            position: 'top',
            labels: {
              ...baseChartOptions.plugins.legend.labels,
              padding: 20,
              font: { size: 13, weight: '600' }
            }
          }
        },
        scales: {
          r: {
            min: 0,
            max: 100,
            grid: {
              color: 'rgba(255, 107, 53, 0.15)',
              drawTicks: true,
              lineWidth: 2
            },
            ticks: {
              color: 'rgba(255, 255, 255, 0.6)',
              font: { size: 12, weight: '600' },
              backdropColor: 'transparent',
              stepSize: 20
            },
            pointLabels: {
              color: 'rgba(255, 255, 255, 0.85)',
              font: { size: 13, weight: '700' },
              padding: 15
            }
          }
        }
      }
    });
  } catch (error) {
    console.error('Failed to render radar chart:', error);
  }
};

/**
 * Render Salary Chart
 */
window.renderSalaryChart = async function() {
  const ctx = document.getElementById('salaryChart');
  if (!ctx) return;

  try {
    const salaries = await fetchAPI('/api/salaries?group_by=department');
    const topSalaries = salaries.slice(0, 10);

    const data = {
      labels: topSalaries.map(s => {
        const name = s.label;
        return name.length > 25 ? name.substring(0, 25) + '...' : name;
      }),
      datasets: [
        {
          label: 'Min Salary',
          data: topSalaries.map(s => Math.round(s.avg_min)),
          backgroundColor: 'rgba(52, 152, 219, 0.3)',
          borderColor: '#3498DB',
          borderWidth: 1.5,
          borderRadius: 6
        },
        {
          label: 'Max Salary',
          data: topSalaries.map(s => Math.round(s.avg_max)),
          backgroundColor: 'rgba(52, 152, 219, 0.7)',
          borderColor: '#3498DB',
          borderWidth: 1.5,
          borderRadius: 6
        }
      ]
    };

    if (window.salaryChartInstance) {
      window.salaryChartInstance.destroy();
    }

    window.salaryChartInstance = new Chart(ctx, {
      type: 'bar',
      data,
      options: {
        ...baseChartOptions,
        scales: {
          ...baseScalesOptions,
          y: {
            ...baseScalesOptions.y,
            ticks: {
              ...baseScalesOptions.y.ticks,
              callback: function(value) {
                return '$' + (value / 1000).toFixed(0) + 'K';
              }
            }
          }
        }
      }
    });
  } catch (error) {
    console.error('Failed to render salary chart:', error);
  }
};

/**
 * Render State Pay Chart
 */
window.renderStatePayChart = async function() {
  const ctx = document.getElementById('statePayChart');
  if (!ctx) return;

  try {
    const salaries = await fetchAPI('/api/salaries?group_by=state');
    const topStates = salaries.slice(0, 12);

    const data = {
      labels: topStates.map(s => s.label),
      datasets: [{
        label: 'Average Salary',
        data: topStates.map(s => Math.round(s.avg_max)),
        backgroundColor: chartColorsArray.slice(0, topStates.length),
        borderColor: 'rgba(255, 107, 53, 0.2)',
        borderWidth: 1.5,
        borderRadius: 8,
        hoverBackgroundColor: 'rgba(255, 107, 53, 0.2)'
      }]
    };

    if (window.statePayChartInstance) {
      window.statePayChartInstance.destroy();
    }

    window.statePayChartInstance = new Chart(ctx, {
      type: 'bar',
      data,
      options: baseChartOptions
    });
  } catch (error) {
    console.error('Failed to render state pay chart:', error);
  }
};

/**
 * Render Geographic Chart
 */
window.renderGeoChart = async function() {
  const ctx = document.getElementById('geoChart');
  if (!ctx) return;

  try {
    const locations = await fetchAPI('/api/locations');
    const topLocations = locations.slice(0, 15);

    const data = {
      labels: topLocations.map(l => l.location_state),
      datasets: [{
        label: 'Job Postings',
        data: topLocations.map(l => l.count),
        backgroundColor: chartColorsArray.slice(0, topLocations.length),
        borderColor: 'rgba(255, 107, 53, 0.2)',
        borderWidth: 1.5,
        borderRadius: 6
      }]
    };

    if (window.geoChartInstance) {
      window.geoChartInstance.destroy();
    }

    window.geoChartInstance = new Chart(ctx, {
      type: 'bar',
      data,
      options: baseChartOptions
    });
  } catch (error) {
    console.error('Failed to render geo chart:', error);
  }
};

/**
 * Render Remote Work
 */
window.renderRemoteWork = async function() {
  const container = document.getElementById('remoteBars');
  if (!container) return;

  try {
    const locations = await fetchAPI('/api/locations');
    const remoteData = locations.slice(0, 10).map(loc => ({
      code: loc.location_state,
      percentage: Math.round((loc.remote_count / loc.count) * 100)
    }));

    container.innerHTML = `
      <div class="remote-list">
        ${remoteData.map(state => `
          <div class="remote-item">
            <span class="remote-state">${state.code}</span>
            <div class="remote-bar-container">
              <div class="remote-bar" style="width: ${state.percentage}%"></div>
            </div>
            <span class="remote-percentage">${state.percentage}%</span>
          </div>
        `).join('')}
      </div>
    `;
  } catch (error) {
    console.error('Failed to render remote work:', error);
    showError('remoteBars');
  }
};

/**
 * Render State Table
 */
window.renderStateTable = async function() {
  const container = document.getElementById('stateTable');
  if (!container) return;

  try {
    const locations = await fetchAPI('/api/locations');
    const stateData = locations.slice(0, 10).map(loc => ({
      state: loc.location_state,
      jobs: loc.count,
      remote: Math.round((loc.remote_count / loc.count) * 100),
      salary: `$${Math.round(loc.avg_salary / 1000)}K`
    }));

    container.innerHTML = `
      <table class="state-table">
        <thead>
          <tr>
            <th>State</th>
            <th>Postings</th>
            <th>Remote %</th>
            <th>Avg Salary</th>
          </tr>
        </thead>
        <tbody>
          ${stateData.map(row => `
            <tr>
              <td><span class="state-code">${row.state}</span></td>
              <td>${row.jobs}</td>
              <td style="color: #1ABC9C; font-weight: 700;">${row.remote}%</td>
              <td>${row.salary}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (error) {
    console.error('Failed to render state table:', error);
    showError('stateTable');
  }
};

/**
 * Render Recent Jobs
 */
window.renderRecentJobs = async function() {
  const container = document.getElementById('recentJobs');
  if (!container) return;

  try {
    const jobs = await fetchAPI('/api/jobs/recent?limit=5');

    container.innerHTML = jobs.map(job => `
      <div class="recent-job-item">
        <div class="job-title">${job.title}</div>
        <div class="job-dept">${job.organization} - ${job.location_state}</div>
        <div class="job-meta">
          <span class="job-badge">$${job.min_salary}-$${job.max_salary}</span>
          <span class="job-badge">${job.telework_eligible ? 'Remote' : 'On-Site'}</span>
          <span class="job-badge">${job.job_grade || 'N/A'}</span>
        </div>
      </div>
    `).join('');
  } catch (error) {
    console.error('Failed to render recent jobs:', error);
    showError('recentJobs');
  }
};

/**
 * Render ESCO Stats
 */
window.renderEscoStats = async function() {
  const container = document.getElementById('escoStats');
  if (!container) return;

  try {
    const skills = await fetchAPI('/api/skills/top?limit=100');
    const matched = skills.filter(s => s.type === 'knowledge' || s.type === 'competence').length;
    const matchRate = skills.length > 0 ? Math.round((matched / skills.length) * 100) : 0;

    container.innerHTML = `
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
        <div style="text-align: center; padding: 1rem;">
          <div style="font-size: 2rem; font-weight: 900; color: #FF6B35;">${matchRate}%</div>
          <div style="font-size: 0.8rem; color: rgba(255,255,255,0.6);">ESCO Match</div>
        </div>
        <div style="text-align: center; padding: 1rem;">
          <div style="font-size: 2rem; font-weight: 900; color: #FF6B35;">${skills.length}</div>
          <div style="font-size: 0.8rem; color: rgba(255,255,255,0.6);">Skills Found</div>
        </div>
      </div>
    `;
  } catch (error) {
    console.error('Failed to render ESCO stats:', error);
    showError('escoStats');
  }
};

/**
 * Render Skill Filters
 */
window.renderSkillFilters = async function() {
  const container = document.getElementById('skillFilters');
  if (!container) return;

  try {
    const skills = await fetchAPI('/api/skills/top?limit=50');
    const types = new Set(skills.map(s => s.type));

    container.innerHTML = Array.from(types).map(type => `
      <button class="filter-btn" style="padding: 0.5rem 1rem; background: rgba(255,107,53,0.08); border: 1.5px solid rgba(255,107,53,0.2); border-radius: 20px; color: rgba(255,255,255,0.7); cursor: pointer; font-size: 0.8rem; font-weight: 600; text-transform: capitalize;">${type}</button>
    `).join('');
  } catch (error) {
    console.error('Failed to render skill filters:', error);
  }
};

/**
 * Render Skills List
 */
window.renderSkillsList = async function() {
  const container = document.getElementById('skillsList');
  if (!container) return;

  try {
    const skills = await fetchAPI('/api/skills/top?limit=20');

    container.innerHTML = skills.map(skill => `
      <div class="skill-item">
        <div class="skill-name">${skill.skill}</div>
        <span class="skill-tag ${skill.type}">${skill.type}</span>
        <div class="skill-count">${skill.count}</div>
      </div>
    `).join('');
  } catch (error) {
    console.error('Failed to render skills list:', error);
    showError('skillsList');
  }
};

/**
 * Render Pay Grades
 */
window.renderPayGrades = async function() {
  const container = document.getElementById('gradeCards');
  if (!container) return;

  try {
    const grades = await fetchAPI('/api/salaries?group_by=grade');

    container.innerHTML = grades.map((grade, idx) => `
      <div class="pay-grade-card" style="animation: fadeInUp ${0.2 + idx * 0.05}s ease-out; opacity: 0; animation-fill-mode: forwards;">
        <div class="pay-grade-code">${grade.label}</div>
        <div class="pay-grade-min">$${Math.round(grade.avg_min/1000)}K</div>
        <div class="pay-grade-max">$${Math.round(grade.avg_max/1000)}K</div>
      </div>
    `).join('');
  } catch (error) {
    console.error('Failed to render pay grades:', error);
    showError('gradeCards');
  }
};

// ============================================================================
// INITIALIZATION
// ============================================================================

console.log('✅ LABO Dashboard JS loaded - API-driven');
