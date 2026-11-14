import identity as ID

SAME = [("https://boards.greenhouse.io/cloudflare/jobs/8245211?gh_src=abc", "https://job-boards.greenhouse.io/cloudflare/jobs/8245211"),
        ("https://careers.withwaymo.com/jobs?gh_jid=7001", "https://boards.greenhouse.io/waymo/jobs/7001"),
        ("https://lseg.wd3.myworkdayjobs.com/en-US/Graduate_Careers/job/London-United-Kingdom/Intern---Software-Engineer_R0124267",
         "https://lseg.wd3.myworkdayjobs.com/Careers/job/Intern---Software-Engineer_R0124267?source=x")]
DIFFERENT = [("https://careers.withwaymo.com/jobs?gh_jid=7001", "https://careers.withwaymo.com/jobs?gh_jid=7002"),
             ("https://boards.greenhouse.io/embed/job_app?token=111", "https://boards.greenhouse.io/embed/job_app?token=222"),
             ("https://careers.ibm.com/careers/JobDetail?jobId=1", "https://careers.ibm.com/careers/JobDetail?jobId=2"),
             ("https://lseg.wd3.myworkdayjobs.com/Careers/job/Intern---Software-Engineer_R0124267",
              "https://lseg.wd3.myworkdayjobs.com/Careers/job/Intern---Software-Engineer_R0124266-1"),
             ("https://boards.greenhouse.io/cloudflare/jobs/8245211", "https://boards.greenhouse.io/cloudflare/jobs/8199958"),
             ("https://careers.oracle.com/jobs/#en/sites/jobsearch/job/312345", "https://careers.oracle.com/jobs/#en/sites/jobsearch/job/399999")]
for a, b in SAME:
    check(ID.key_of(a) == ID.key_of(b), f"identity: same vacancy {a[:60]}", f"{ID.key_of(a)} vs {ID.key_of(b)}")
for a, b in DIFFERENT:
    check(ID.key_of(a) != ID.key_of(b), f"identity: different vacancies {a[:60]}", str(ID.key_of(a)))
check(ID.key_of("https://go.vansh.nyc/abc") is None and ID.key_of("https://www.linkedin.com/jobs/view/1") is None, "identity: list links carry no requisition")
check(ID.nurl("https://x.com/careers/?utm_source=a#openings") == ID.nurl("https://x.com/careers"), "identity: tracking and anchors dropped")
check(ID.no_read("https://www.linkedin.com/jobs/view/1") and not ID.no_read("https://boards.greenhouse.io/x/jobs/1"), "identity: sites not read")
