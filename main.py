import os
import random
from langchain_openai import ChatOpenAI
from crewai import LLM, Agent, Process, Crew, Task
from crewai_tools import ScrapeWebsiteTool, SerperDevTool
import readline
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY_AI_AGENTS"]
os.environ["SERPER_API_KEY"] = os.environ["SERPER_API_KEY"]

llm = ChatOpenAI(model = "gpt-4o", temperature = 0.5)
# A high temperature so the Interview Coach writes a different set of questions on every run
question_llm = LLM(model = "gpt-4o", temperature = 1.0)

number_of_questions = 100
questions_file = "reports/Questions.md"

class InterviewEnded(BaseException):
    """Raised when the candidate types `quit`. A BaseException so CrewAI's tool error handling doesn't swallow it."""

class AskCandidateInput(BaseModel):
    question: str = Field(..., description = "The single interview question to ask the candidate")
    feedback_on_previous_answer: str = Field("", description = "The Interview Coach's feedback on the candidate's previous answer, if any")

class AskCandidateTool(BaseTool):
    name: str = "Ask Candidate"
    description: str = "Shows feedback on the previous answer, asks the candidate one interview question in the terminal, and returns their answer"
    args_schema: type[BaseModel] = AskCandidateInput

    def _run(self, question: str, feedback_on_previous_answer: str = "") -> str:
        if feedback_on_previous_answer:
            print(f"\nFeedback:\n\n{feedback_on_previous_answer}\n")
        print(f"\nQuestion: {question}\n")
        answer = input("> ").strip()
        if answer.lower() == "quit":
            raise InterviewEnded()
        return answer

interviewer = input("Enter the name of the interviewer: ").strip()
interviewer_role = input("Enter the role of the interviewer: ").strip()
company = input("Enter the name of the company: ").strip()
job_position = input("Enter the job position: ").strip()
job_description = input("Enter the job description: ").strip()

print(f"\n### Agent running...")

# Changes on every run so each kickoff produces a different set of questions
question_seed = random.randint(1, 1_000_000)

# Research AI Agent
research_agent = Agent(
    role = "Research Agent",
    goal = "Conduct in-depth research",
    backstory = """
    As a Research Specialist, your mission is to uncover detailed and relevant information.
    The ultimate goal is to meet the expectations of the task
    """,
    llm = llm.model_name,
    tools = [ScrapeWebsiteTool(), SerperDevTool()],
)

research_company_task = Task(
    description = f"""
    Research about {company}, their position in the sector and recent industry trends.
    Focus on recent news and developments within the last 12months
    """,
    expected_output = f"A comprehensive report in Markdown with bullet point about {company} and its industry",
    agent = research_agent,
    output_file = f"reports/{company}.md"
)

research_interviewer_task = Task(
    description = f"Research about {interviewer}, with a focus on their professional career",
    expected_output = f"A comprehensive report in Markdown with bullet point about {interviewer} working in {company} as a {interviewer_role}",
    agent = research_agent,
    output_file = f"reports/{interviewer}.md"
)

# Interview Coach agent
coach_agent = Agent(
    role = "Interview Coach",
    goal = f"Help user prepare for {job_position} interview",
    backstory = f"""
    You are an expert interview specialist who helps candidates prepare for job interviews.
    You dig into companies and interviewers using credible, recent sources, and turn your
    findings into clear, practical insights and questions a candidate can use in the interview.
    """,
    llm = question_llm,
)

questions_task = Task(
    description = f"""
    Write the questions that {interviewer}, {interviewer_role} at {company}, would realistically ask
    a candidate for the {job_position} position.
    Job description: {job_description}

    Write every question from the interviewer's point of view, shaped by their role:
    - A technical interviewer (engineer, staff/principal engineer, architect, tech lead) asks deep,
      hands-on questions about the tools, systems and problems named in the job description:
      design trade-offs, production incidents, debugging, scaling, security and how the candidate would
      build or improve specific parts of {company}'s systems.
    - A manager or director asks about delivery, prioritisation, ownership, collaboration with other teams
      and handling ambiguity, still grounded in the job's technical work.
    - A recruiter, HR or people partner asks about motivation, culture fit, career path and ways of working.
    Use the interviewer research to reflect their own background and interests, and the company research
    to tie questions to {company}'s products, industry and recent developments.

    Every question must be open-ended and detailed:
    - Never answerable with yes/no, a single fact or a one-line definition.
    - Prefer realistic scenarios ("Imagine...", "Walk me through...", "How would you design...",
      "Tell me about a time...") with enough context that the candidate has to explain their reasoning,
      the trade-offs they would weigh and the outcome.
    - Name the specific technologies, constraints or situations from the job description instead of
      asking generic questions.
    - Ask one main question per item. You may add a short follow-up clause that asks the candidate to go
      deeper, but don't stack several unrelated questions together.

    Make this set different from any previous session (session seed: {question_seed}):
    - Decide the focus areas yourself from what {interviewer_role} would care about most, and vary them between sessions.
    - Mix the topics and question styles throughout the list, and invent fresh scenarios rather than
      reusing common interview questions.
    - Never repeat a question or ask the same thing twice in different words.
    """,
    expected_output = f"""
    A numbered Markdown list of exactly {number_of_questions} open-ended, detailed interview questions as {interviewer} ({interviewer_role})
    would ask them, weighted towards the interviewer's area of expertise and covering:
    role-specific technical or functional depth (most of the questions), real-world scenarios and past experience,
    collaboration and ways of working, and culture fit and growth mindset at {company}.
    Under each question, add one line in italics starting with "What a strong answer covers:" listing the key points.
    """,
    agent = coach_agent,
    context = [research_company_task, research_interviewer_task]
)

interviewer_agent = Agent(
    role = "Interviewer Agent",
    goal = f"Run a realistic mock interview for the {job_position} position at {company}, asking every prepared question one at a time",
    backstory = f"""
    You are {interviewer}, {interviewer_role} at {company}, and an experienced interviewer.
    You interview the way someone in your role would: you ask open-ended questions that make the candidate
    explain their reasoning, and you probe for depth and real experience rather than textbook definitions.
    You ask one question at a time, wait for the candidate's answer, and make sure every answer
    is reviewed by the Interview Coach before moving on to the next question.
    """,
    llm = llm.model_name,
    tools = [AskCandidateTool()],
    allow_delegation = True,
    max_iter = number_of_questions * 4
)

interview_task = Task(
    description = f"""
    Conduct a mock interview for the {job_position} position at {company} using the prepared questions.
    Job description: {job_description}

    Follow this loop strictly, in order, for every question:
    1. Use the Ask Candidate tool to ask exactly one question, phrased in your own voice as {interviewer_role}.
       Keep it open-ended and include the scenario or context from the prepared question, but don't show
       the "What a strong answer covers" notes to the candidate. From the second question onward,
       pass the Interview Coach's feedback on the previous answer in the feedback_on_previous_answer field.
    2. Delegate to the Interview Coach: give them the question and the candidate's exact answer,
       and ask for feedback on what was good, what could be improved, and how to take the answer
       to the next level, with a short example of a stronger answer.
    3. Only then move on to the next question.

    If the candidate answers "skip", move to the next question without feedback.
    Ask every prepared question, in the order given, until all {number_of_questions} are done or the candidate stops.
    After the last question, use the Ask Candidate tool one final time to share the feedback on the last answer,
    with the question set to "That was the last question. Press Enter to finish."
    Never ask more than one question at a time and never invent the candidate's answers.
    """,
    expected_output = """
    A Markdown interview transcript listing every question asked, the candidate's answer,
    and the Interview Coach's feedback, followed by an overall summary of strengths and areas to improve
    """,
    agent = interviewer_agent,
    context = [questions_task],
)

crew = Crew(
    agents = [research_agent, coach_agent, interviewer_agent],
    tasks = [research_company_task, research_interviewer_task, questions_task, interview_task],
    verbose = False, # Change to true if you want details
    process = Process.sequential
)

def write_questions_file():
    if questions_task.output is None:
        print("No questions were generated, so there's nothing to save.")
        return
    os.makedirs(os.path.dirname(questions_file), exist_ok = True)
    with open(questions_file, "w") as file:
        file.write(f"# {job_position} interview questions\n\n")
        file.write(f"Prepared for an interview with {interviewer} ({interviewer_role}) at {company}.\n\n")
        file.write(questions_task.output.raw.strip() + "\n")
    print(f"All the generated questions have been saved to {questions_file}")

def main():
    try:
        crew.kickoff()
    except InterviewEnded:
        print("\nInterview ended.")
        write_questions_file()

if __name__ == "__main__":
    main()