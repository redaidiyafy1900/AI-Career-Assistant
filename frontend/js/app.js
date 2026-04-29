// 等待DOM加载完成后再执行所有代码
document.addEventListener('DOMContentLoaded', function () {
    // 获取DOM元素
    const featureCards = document.querySelectorAll('.feature-card');
    const featureDetail = document.getElementById('feature-detail');
    const detailContent = document.getElementById('detail-content');
    const backButton = document.getElementById('back-button');
    const featuresContainer = document.querySelector('.features');

    // 简历解析相关元素 - 直接引用现有DOM
    const resumeParserContent = document.getElementById('resume-parser-content');

    // 功能详情内容
    const featureDetails = {
        'interview-coach': {
            title: '面试辅导',
            content: '' // 留空，稍后加载外部HTML
        },

    };

    // 添加加载外部HTML的函数
    // 修改前
    function loadInterviewCoachContent() {
        return fetch('frontend/interview_coach.html')
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.text();
            })
            .catch(error => {
                console.error('There has been a problem with your fetch operation:', error);
                return '<div class="error-message">加载面试辅导内容失败，请稍后重试。</div>';
            });
    }

    // 修改后
    function loadInterviewCoachContent() {
        return fetch('/interview_coach.html')
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.text();
            })
            .catch(error => {
                console.error('There has been a problem with your fetch operation:', error);
                return '<div class="error-message">加载面试辅导内容失败，请稍后重试。</div>';
            });
    }

    // 初始化简历解析功能
    function initializeResumeParser() {
        const uploadArea = document.querySelector('.upload-area');
        const fileInput = document.getElementById('resume-upload');
        const analyzeBtn = document.getElementById('analyze-btn');
        const analysisResults = document.getElementById('analysis-results');
        const fileNameDisplay = document.getElementById('file-name-display');
        const uploadText = document.getElementById('upload-text');

        if (!uploadArea || !fileInput || !analyzeBtn) {
            console.error('无法找到简历解析相关元素');
            return;
        }

        // 重置显示状态
        analysisResults.style.display = 'none';
        fileNameDisplay.style.display = 'none';
        uploadText.style.display = 'block';

        // 文件选择事件
        fileInput.onchange = function (e) {
            if (this.files && this.files.length > 0) {
                const file = this.files[0];
                fileNameDisplay.textContent = '已选择文件：' + file.name;
                fileNameDisplay.style.display = 'block';
                uploadText.style.display = 'none';
                console.log('文件已选择:', file.name);
            }
        };

        // 上传区域点击事件 - 只在点击非按钮区域时触发文件选择
        uploadArea.onclick = function (e) {
            e.stopPropagation();
            // 只有当点击的不是分析按钮或其内部元素时才触发文件选择
            if (!e.target.closest('#analyze-btn')) {
                fileInput.click();
            }
        };

        // 拖拽上传功能
        uploadArea.ondragover = function (e) {
            e.preventDefault();
            e.stopPropagation();
            e.dataTransfer.dropEffect = 'copy';
            this.style.borderColor = '#2196F3';
            this.style.backgroundColor = 'rgba(33, 150, 243, 0.1)';
        };

        uploadArea.ondragleave = function (e) {
            e.preventDefault();
            e.stopPropagation();
            this.style.borderColor = '#3498db';
            this.style.backgroundColor = 'transparent';
        };

        // 拖拽上传处理 - 兼容各浏览器
        uploadArea.ondrop = function (e) {
            e.preventDefault();
            e.stopPropagation();
            this.style.borderColor = '#3498db';
            this.style.backgroundColor = 'transparent';

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                // 显式设置文件输入的值
                const dt = new DataTransfer();
                dt.items.add(files[0]);
                fileInput.files = dt.files;

                fileNameDisplay.textContent = '已选择文件：' + files[0].name;
                fileNameDisplay.style.display = 'block';
                uploadText.style.display = 'none';
                console.log('文件已拖拽上传:', files[0].name);
            }
        };

        // 替换分析按钮的完整处理逻辑
        analyzeBtn.onclick = function (e) {
            e.stopPropagation();
            e.preventDefault();

            if (fileInput.files.length === 0) {
                alert('请先选择或拖拽上传简历文件');
                return;
            }

            // 显示加载状态
            analysisResults.style.display = 'block';
            document.querySelector('.score-display').innerHTML = '<h3>正在分析中...</h3>';
            console.log('开始分析文件:', fileInput.files[0].name);

            // 创建FormData对象
            const formData = new FormData();
            formData.append('resume', fileInput.files[0]);
            if (document.getElementById('job-description')) {
                formData.append('jobDescription', document.getElementById('job-description').value);
            }

            // 调用后端API
            fetch('/api/analyze-resume', {
                method: 'POST',
                body: formData
            })
                .then(response => response.json())
                .then(data => {
                    console.log('收到分析结果:', data);

                    // ✅ 检查是否有错误
                    if (data.error) {
                        console.error('分析出错:', data.error);
                        document.querySelector('.score-display').innerHTML = `<h3>分析失败: ${data.error}</h3>`;
                        return;
                    }

                    // 直接使用服务器返回的解析好的数据
                    let realScore = data.data.overallScore || 75;
                    let realProfileData = [6.0, 5.5, 7.8]; // 技能指数、经验指数、性格指数
                    let realSuggestions = data.data.improvements || ["建议增加项目经验", "可提升专业技能", "优化简历格式"];
                    let radarData = [75, 70, 75, 70, 75]; // 雷达图保持五项数据

                    console.log('直接使用服务器返回的数据:', data.data);
                    console.log('总分:', realScore);
                    console.log('改进建议:', realSuggestions);

                    // 从服务器返回的数据中提取三项指数
                    if (data.data.dimensions) {
                        realProfileData = [
                            data.data.dimensions.skills / 10 || 6.0,  // 转换为十分制
                            data.data.dimensions.experience / 10 || 5.5,
                            data.data.dimensions.certifications / 10 || 7.8  // 使用certifications作为性格指数
                        ];
                        console.log('解析到三项指数:', realProfileData);
                    }

                    // 从服务器返回的数据中提取雷达图数据
                    if (data.data.dimensions) {
                        radarData = [
                            data.data.dimensions.skills || 75,
                            data.data.dimensions.projects || 70,
                            data.data.dimensions.education || 75,
                            data.data.dimensions.certifications || 70,
                            data.data.dimensions.experience || 75
                        ];
                        console.log('解析到雷达图数据:', radarData);
                    }

                    // ✅ 使用真实数据更新UI
                    document.querySelector('.score-display').innerHTML = `<h3>简历评分: ${realScore}/100</h3>`;
                    document.querySelector('.profile-chart').innerHTML = '<canvas id="profileChart" width="300" height="200"></canvas>';
                    document.querySelector('.radar-chart').innerHTML = '<canvas id="radarChart" width="300" height="200"></canvas>';

                    // ✅ 显示改进建议
                    const suggestionsHTML = realSuggestions.map(s => `<li>${s}</li>`).join('');
                    document.querySelector('.suggestions').innerHTML = `<h4>改进建议:</h4><ul>${suggestionsHTML}</ul>`;

                    // ✅ 等待Chart.js加载完成
                    if (typeof Chart !== 'undefined') {
                        renderCharts(realScore, realProfileData, radarData);
                    } else {
                        // 如果Chart.js未加载，显示文字版数据
                        document.querySelector('.profile-chart').innerHTML = `
                            <div style="padding: 20px;">
                                <h4>三项指数评分</h4>
                                <p>技能指数: ${realProfileData[0]}/10</p>
                                <p>经验指数: ${realProfileData[1]}/10</p>
                                <p>性格指数: ${realProfileData[2]}/10</p>
                            </div>
                        `;
                    }

                    // 添加岗位推荐功能
                    addJobRecommendation(data.data);
                    
                    // 添加滚动效果
                    analysisResults.scrollIntoView({ behavior: 'smooth' });
                })
                .catch(error => {
                    console.error('分析请求失败:', error);
                    document.querySelector('.score-display').innerHTML = '<h3>分析失败，请稍后重试</h3>';
                });
        };

        // ✅ 添加图表渲染函数
        // ✅ 修改图表渲染函数，实现横向柱状图
        function renderCharts(score, profileData, radarData) {
            // ✅ 量化画像图表（横向柱状图）
            const profileCtx = document.getElementById('profileChart').getContext('2d');
            const profileChart = new Chart(profileCtx, {
                type: 'bar',
                data: {
                    labels: ['技能指数', '经验指数', '性格指数'],
                    datasets: [{
                        label: '评分',
                        data: profileData,
                        backgroundColor: [
                            'rgba(54, 162, 235, 0.7)',
                            'rgba(75, 192, 192, 0.7)',
                            'rgba(153, 102, 255, 0.7)'
                        ],
                        borderColor: [
                            'rgba(54, 162, 235, 1)',
                            'rgba(75, 192, 192, 1)',
                            'rgba(153, 102, 255, 1)'
                        ],
                        borderWidth: 1
                    }]
                },
                options: {
                    // ✅ 设置为横向柱状图
                    indexAxis: 'y',
                    scales: {
                        x: {
                            beginAtZero: true,
                            max: 10
                        }
                    },
                    responsive: true,
                    maintainAspectRatio: false
                }
            });

            // ✅ 为横向柱状图添加鼠标悬浮放大效果
            const profileCanvas = document.getElementById('profileChart');
            profileCanvas.addEventListener('mouseover', function () {
                this.style.transform = 'scale(1.2)';
                this.style.transition = 'transform 0.3s ease';
                this.style.zIndex = '10';
            });
            profileCanvas.addEventListener('mouseout', function () {
                this.style.transform = 'scale(1)';
                this.style.zIndex = '1';
            });

            // ✅ 雷达图配置，优化悬浮交互效果
            const radarCtx = document.getElementById('radarChart').getContext('2d');
            const radarChart = new Chart(radarCtx, {
                type: 'radar',
                data: {
                    labels: ['专业技能', '项目经验', '行业认知', '创新技能', '团队协作'],
                    datasets: [{
                        label: '技能评分',
                        data: radarData,
                        backgroundColor: 'rgba(153, 102, 255, 0.2)',
                        borderColor: 'rgba(153, 102, 255, 1)',
                        pointBackgroundColor: 'rgba(153, 102, 255, 1)',
                        pointBorderColor: '#fff',
                        pointHoverBackgroundColor: '#fff',
                        pointHoverBorderColor: 'rgba(153, 102, 255, 1)',
                        pointHoverRadius: 6,  // 增大悬浮点半径
                        pointRadius: 4  // 增大常规点半径
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        r: {
                            beginAtZero: true,
                            max: 100,
                            ticks: {
                                stepSize: 20
                            }
                        }
                    },
                    plugins: {
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            backgroundColor: 'rgba(0, 0, 0, 0.7)',
                            titleFont: {
                                size: 14
                            },
                            bodyFont: {
                                size: 13
                            },
                            padding: 10,
                            cornerRadius: 4
                        }
                    },
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    }
                }
            });

            // ✅ 为雷达图添加鼠标悬浮放大效果
            const radarCanvas = document.getElementById('radarChart');
            radarCanvas.addEventListener('mouseover', function () {
                this.style.transform = 'scale(1.2)';
                this.style.transition = 'transform 0.3s ease';
                this.style.zIndex = '10';
            });
            radarCanvas.addEventListener('mouseout', function () {
                this.style.transform = 'scale(1)';
                this.style.zIndex = '1';
            });
        }
    }
    
    // 岗位推荐功能
    function addJobRecommendation(analysisData) {
        // 创建岗位推荐区域
        const recommendationsSection = document.createElement('div');
        recommendationsSection.className = 'detail-section';
        recommendationsSection.innerHTML = `
            <h3>岗位推荐</h3>
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-top: 20px;">
                <h4>根据您的简历分析结果，我们为您推荐以下岗位：</h4>
                <div id="job-recommendations" style="margin-top: 15px;">
                    <p style="text-align: center; color: #666;">正在生成推荐岗位...</p>
                </div>
            </div>
        `;
        
        // 在改进建议后添加岗位推荐
        const suggestionsSection = document.querySelector('.suggestions');
        if (suggestionsSection) {
            suggestionsSection.insertAdjacentElement('afterend', recommendationsSection);
        }
        
        // 从jobs.json加载真实岗位数据
        fetch('/data/jobs.json')
            .then(response => response.json())
            .then(data => {
                const jobs = data.jobs || [];
                
                // 模拟岗位推荐过程
                setTimeout(() => {
                    const recommendationsContainer = document.getElementById('job-recommendations');
                    
                    if (jobs.length > 0) {
                        // 基于简历分析结果进行岗位匹配
                        const matchedJobs = matchJobsWithResume(analysisData, jobs);
                        
                        if (matchedJobs.length > 0) {
                            let recommendationsHTML = '';
                            matchedJobs.forEach((job, index) => {
                                recommendationsHTML += `
                                    <div style="padding: 15px; border-bottom: 1px solid #eee; margin-bottom: 10px;">
                                        <h5 style="margin: 0 0 5px 0; color: #4a90e2;">${index + 1}. ${job.job.title} - ${job.job.company}</h5>
                                        <p style="margin: 0 0 5px 0;">薪资：${job.job.salary} | 地点：${job.job.location}</p>
                                        <p style="margin: 0 0 5px 0; font-size: 0.9em; color: #666;">经验要求：${job.job.experience} | 招聘人数：${job.job.count}人</p>
                                        <p style="margin: 0 0 10px 0; font-size: 0.9em; color: #666;">${job.job.description}</p>
                                        ${job.job.skills.length > 0 ? `
                                            <div style="font-size: 0.85em; color: #888;">
                                                <strong>技能要求：</strong>${job.job.skills.join(', ')}
                                            </div>
                                        ` : ''}
                                        <div style="font-size: 0.8em; color: #4a90e2; margin-top: 5px;">
                                            <strong>匹配度：</strong>${Math.round(job.score * 100)}%
                                        </div>
                                    </div>
                                `;
                            });
                            recommendationsContainer.innerHTML = recommendationsHTML;
                        } else {
                            recommendationsContainer.innerHTML = '<p style="text-align: center; color: #666;">暂无匹配的岗位推荐</p>';
                        }
                    } else {
                        recommendationsContainer.innerHTML = '<p style="text-align: center; color: #666;">暂无匹配的岗位推荐</p>';
                    }
                }, 1000);
            })
            .catch(error => {
                console.error('加载岗位数据失败:', error);
                const recommendationsContainer = document.getElementById('job-recommendations');
                recommendationsContainer.innerHTML = '<p style="text-align: center; color: #666;">岗位数据加载失败</p>';
            });
    }
    
    // 根据简历分析结果匹配岗位
    function matchJobsWithResume(analysisData, jobs) {
        // 提取简历中的技能和经验信息
        const resumeSkills = extractSkillsFromAnalysis(analysisData);
        const resumeExperience = extractExperienceFromAnalysis(analysisData);
        
        // 计算每个岗位的匹配度
        const matchedJobs = jobs.map(job => {
            let score = 0;
            
            // 技能匹配度
            if (job.skills && job.skills.length > 0) {
                const matchedSkills = job.skills.filter(skill => 
                    resumeSkills.some(resumeSkill => 
                        resumeSkill.toLowerCase().includes(skill.toLowerCase()) || 
                        skill.toLowerCase().includes(resumeSkill.toLowerCase())
                    )
                );
                score += (matchedSkills.length / job.skills.length) * 50;
            } else {
                // 不限技能的岗位给予基础分
                score += 30;
            }
            
            // 经验匹配度
            if (job.experience) {
                if (job.experience.includes('本科') && resumeExperience.includes('本科')) {
                    score += 20;
                }
                if (job.experience.includes('硕士') && resumeExperience.includes('硕士')) {
                    score += 30;
                }
            }
            
            // 其他因素
            score += 20; // 基础分
            
            return { job, score };
        });
        
        // 按匹配度排序，返回前5个
        return matchedJobs
            .sort((a, b) => b.score - a.score)
            .filter(job => job.score > 30) // 只返回匹配度大于30的岗位
            .slice(0, 5);
    }
    
    // 从分析结果中提取技能信息
    function extractSkillsFromAnalysis(analysisData) {
        const skills = [];
        
        // 从改进建议中提取技能
        if (analysisData.improvements) {
            analysisData.improvements.forEach(improvement => {
                // 提取可能的技能关键词
                const skillKeywords = improvement.match(/[A-Za-z]+(?:\s+[A-Za-z]+)*/g) || [];
                skills.push(...skillKeywords);
            });
        }
        
        // 从维度评分中提取技能
        if (analysisData.dimensions) {
            for (const [key, value] of Object.entries(analysisData.dimensions)) {
                if (value > 70) {
                    skills.push(key);
                }
            }
        }
        
        // 添加一些通用技能关键词
        skills.push('沟通', '团队合作', '问题解决', '学习能力');
        
        return skills.map(skill => skill.trim()).filter(Boolean);
    }
    
    // 从分析结果中提取经验信息
    function extractExperienceFromAnalysis(analysisData) {
        let experience = '本科';
        
        // 从维度评分中判断经验水平
        if (analysisData.dimensions) {
            if (analysisData.dimensions.experience > 80) {
                experience += ' 有经验';
            }
        }
        
        return experience;
    }

    // 为每个功能卡片添加点击事件
    featureCards.forEach(card => {
        card.addEventListener('click', function () {
            const featureId = this.id;

            if (featureId === 'resume-parser') {
                // 显示简历解析内容
                resumeParserContent.classList.remove('hidden');
                detailContent.innerHTML = '';
                detailContent.appendChild(resumeParserContent);
                initializeResumeParser();
            } else if (featureId === 'interview-coach') {
                // 加载面试辅导外部HTML
                resumeParserContent.classList.add('hidden');
                detailContent.innerHTML = '<div class="loading">加载中...</div>';
                loadInterviewCoachContent().then(html => {
                    detailContent.innerHTML = html;
                    // 为新加载的内容中的链接添加target="_blank"属性
                    document.querySelectorAll('#detail-content a').forEach(link => {
                        link.setAttribute('target', '_blank');
                    });
                });
            } else {
                // 显示其他功能内容
                resumeParserContent.classList.add('hidden');
                detailContent.innerHTML = featureDetails[featureId].content;
                

            }

            featuresContainer.classList.add('hidden');
            featureDetail.classList.remove('hidden');
            addDetailStyles();
        });
    });

    // 返回按钮
    backButton.addEventListener('click', function () {
        featureDetail.classList.add('hidden');
        featuresContainer.classList.remove('hidden');
    });

    // 添加样式
    function addDetailStyles() {
        if (!document.getElementById('detail-styles')) {
            const styleSheet = document.createElement('style');
            styleSheet.id = 'detail-styles';
            styleSheet.textContent = `
                /* 蓝色主题变量 */
                :root {
                    --primary-blue: #4a90e2;
                    --light-blue: #6ba3f0;
                    --dark-blue: #357abd;
                    --bg-light: #f8fbff;
                    --text-dark: #2c3e50;
                    --shadow-light: 0 2px 8px rgba(74, 144, 226, 0.1);
                    --shadow-hover: 0 8px 25px rgba(74, 144, 226, 0.15);
                }
    
                /* 页面基础样式 */
                #resume-parser-content {
                    width: 100%;
                    background: linear-gradient(135deg, var(--bg-light) 0%, #ffffff 100%);
                    border-radius: 15px;
                    padding: 30px;
                    box-shadow: var(--shadow-light);
                    transition: all 0.3s ease;
                }
    
                /* 标题区域样式 */
                .detail-section h3 {
                    margin-bottom: 20px;
                    color: var(--primary-blue);
                    font-size: 1.8em;
                    font-weight: 600;
                    text-align: center;
                    position: relative;
                    padding-bottom: 15px;
                }
    
                .detail-section h3::after {
                    content: '';
                    position: absolute;
                    bottom: 0;
                    left: 50%;
                    transform: translateX(-50%);
                    width: 60px;
                    height: 3px;
                    background: linear-gradient(90deg, var(--primary-blue), var(--light-blue));
                    border-radius: 2px;
                }
    
                /* 上传区域样式 */
                .upload-area {
                    border: 2px dashed var(--primary-blue);
                    border-radius: 15px;
                    padding: 50px 40px;
                    text-align: center;
                    margin: 30px 0;
                    cursor: pointer;
                    background: linear-gradient(135deg, #ffffff 0%, var(--bg-light) 100%);
                    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                    position: relative;
                    overflow: hidden;
                }
    
                .upload-area::before {
                    content: '';
                    position: absolute;
                    top: -50%;
                    left: -50%;
                    width: 200%;
                    height: 200%;
                    background: linear-gradient(45deg, transparent, rgba(74, 144, 226, 0.05), transparent);
                    transform: rotate(45deg);
                    transition: all 0.5s;
                    opacity: 0;
                }
    
                .upload-area:hover {
                    background: linear-gradient(135deg, var(--bg-light) 0%, #ffffff 100%);
                    border-color: var(--light-blue);
                    box-shadow: var(--shadow-hover);
                    transform: translateY(-5px);
                }
    
                .upload-area:hover::before {
                    opacity: 1;
                    transform: rotate(45deg) translate(50%, 50%);
                }
    
                .upload-area i {
                    font-size: 4rem;
                    color: var(--primary-blue);
                    margin-bottom: 20px;
                    transition: all 0.3s ease;
                }
    
                .upload-area:hover i {
                    color: var(--light-blue);
                    transform: scale(1.1);
                }
    
                .upload-area p {
                    font-size: 1.3rem;
                    color: var(--text-dark);
                    font-weight: 500;
                    margin-bottom: 10px;
                }
    
                .upload-area .note {
                    font-size: 0.9rem;
                    color: #7f8c8d;
                    margin-top: 10px;
                }
    
                .upload-area input {
                    display: none;
                }
    
                /* 分析按钮样式 */
                #analyze-btn {
                    margin-top: 20px;
                    background: linear-gradient(135deg, var(--primary-blue), var(--dark-blue));
                    color: white;
                    border: none;
                    padding: 15px 40px;
                    font-size: 1.1em;
                    font-weight: 600;
                    border-radius: 25px;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    box-shadow: var(--shadow-light);
                }
    
                #analyze-btn:hover:not(:disabled) {
                    transform: translateY(-3px);
                    box-shadow: var(--shadow-hover);
                }
    
                #analyze-btn:disabled {
                    background: #bdc3c7;
                    cursor: not-allowed;
                    transform: none;
                }
    
                /* 分数显示样式 */
                .score-display {
                    text-align: center;
                    font-size: 1.8em;
                    margin: 30px 0;
                    padding: 30px;
                    background: linear-gradient(135deg, #ffffff 0%, var(--bg-light) 100%);
                    border-radius: 15px;
                    box-shadow: var(--shadow-light);
                    transition: all 0.3s ease;
                }
    
                .score-display:hover {
                    transform: translateY(-3px);
                    box-shadow: var(--shadow-hover);
                }
    
                .score-display h3 {
                    color: var(--primary-blue);
                    margin-bottom: 15px;
                }
    
                /* 图表容器样式 */
                .charts-container {
                    display: flex;
                    justify-content: space-around;
                    flex-wrap: wrap;
                    margin: 30px 0;
                    gap: 30px;
                }
    
                .profile-chart, .radar-chart {
                    flex: 1;
                    min-width: 350px;
                    background: white;
                    border-radius: 15px;
                    padding: 25px;
                    box-shadow: var(--shadow-light);
                    transition: all 0.3s ease;
                    position: relative;
                }
    
                .profile-chart:hover, .radar-chart:hover {
                    transform: translateY(-5px);
                    box-shadow: var(--shadow-hover);
                }
    
                /* 建议区域样式 */
                .suggestions {
                    margin-top: 40px;
                    padding: 30px;
                    background: linear-gradient(135deg, #ffffff 0%, var(--bg-light) 100%);
                    border-radius: 15px;
                    box-shadow: var(--shadow-light);
                    transition: all 0.3s ease;
                }
    
                .suggestions:hover {
                    transform: translateY(-3px);
                    box-shadow: var(--shadow-hover);
                }
    
                .suggestions h4 {
                    color: var(--primary-blue);
                    margin-bottom: 20px;
                    font-size: 1.4em;
                }
    
                /* 不规则emoji装饰 */
                .emoji-decoration {
                    position: absolute;
                    font-size: 2rem;
                    opacity: 0.6;
                    animation: float 3s ease-in-out infinite;
                    pointer-events: none;
                }
    
                .emoji-decoration:nth-child(odd) {
                    animation-delay: -1.5s;
                }
    
                @keyframes float {
                    0%, 100% { transform: translateY(0px) rotate(0deg); }
                    50% { transform: translateY(-20px) rotate(5deg); }
                }
    
                /* 响应式设计 */
                @media (max-width: 768px) {
                    #resume-parser-content {
                        padding: 20px;
                    }
                    
                    .charts-container {
                        flex-direction: column;
                    }
                    
                    .profile-chart, .radar-chart {
                        min-width: auto;
                    }
                    
                    .upload-area {
                        padding: 30px 20px;
                    }
                }
            `;
            document.head.appendChild(styleSheet);

            // 添加emoji装饰
            addEmojiDecorations();
        }
    }

    // 添加emoji装饰函数
    function addEmojiDecorations() {
        const container = document.getElementById('resume-parser-content');
        if (container && !container.querySelector('.emoji-decoration')) {
            const emojis = ['🌟', '📄', '💼', '🎯', '🚀', '💡', '📊', '✨'];
            const positions = [
                { top: '10%', left: '5%' },
                { top: '20%', right: '8%' },
                { bottom: '15%', left: '10%' },
                { bottom: '25%', right: '5%' },
                { top: '50%', left: '3%' },
                { top: '60%', right: '3%' }
            ];

            positions.forEach((pos, index) => {
                const emoji = document.createElement('span');
                emoji.className = 'emoji-decoration';
                emoji.textContent = emojis[index % emojis.length];
                emoji.style.top = pos.top;
                emoji.style.left = pos.left;
                emoji.style.right = pos.right;
                emoji.style.bottom = pos.bottom;
                container.appendChild(emoji);
            });
        }
    }

});
