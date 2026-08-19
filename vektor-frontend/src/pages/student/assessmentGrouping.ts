import type { AssessmentQuestion } from '../../types/assessment';
import type { Competency } from '../../types/competency';

export interface GroupedQuestion extends AssessmentQuestion {
  competencyName: string;
}

export interface Chapter {
  outcomeAreaId: number;
  name: string;
  questions: GroupedQuestion[];
}

/**
 * Вопросы анкеты группируются по «ОР / навык» — тот же уровень, что на
 * экране результатов (5 глав, не 11 критериев и не 8 глав прототипа — см.
 * CLAUDE.md, находка про пересев 8→11). Видны только ОР, реально
 * присутствующие в анкете: список вопросов уже отфильтрован бэком по
 * возрасту субъекта, здесь только группировка.
 */
export function groupQuestionsIntoChapters(
  questions: AssessmentQuestion[],
  competencies: Competency[],
): Chapter[] {
  const competencyById = new Map(competencies.map((c) => [c.id, c]));

  const entries = questions
    .map((question) => {
      const competency = competencyById.get(question.competency_id);
      return competency ? { question, competency } : null;
    })
    .filter((entry): entry is { question: AssessmentQuestion; competency: Competency } => entry !== null)
    .sort(
      (a, b) =>
        a.competency.outcome_area.order - b.competency.outcome_area.order ||
        a.competency.order - b.competency.order ||
        a.question.order - b.question.order,
    );

  const chapters: Chapter[] = [];
  for (const { question, competency } of entries) {
    const last = chapters[chapters.length - 1];
    const groupedQuestion: GroupedQuestion = { ...question, competencyName: competency.name };
    if (last && last.outcomeAreaId === competency.outcome_area.id) {
      last.questions.push(groupedQuestion);
    } else {
      chapters.push({
        outcomeAreaId: competency.outcome_area.id,
        name: competency.outcome_area.name,
        questions: [groupedQuestion],
      });
    }
  }
  return chapters;
}

/** Позиция плоского индекса (по всем главам подряд) внутри списка глав. */
export function locateInChapters(
  chapters: Chapter[],
  flatIndex: number,
): { chapterIndex: number; indexInChapter: number } {
  let cursor = 0;
  for (let ci = 0; ci < chapters.length; ci++) {
    const len = chapters[ci].questions.length;
    if (flatIndex < cursor + len) return { chapterIndex: ci, indexInChapter: flatIndex - cursor };
    cursor += len;
  }
  return { chapterIndex: Math.max(chapters.length - 1, 0), indexInChapter: 0 };
}

/** Первый плоский индекс главы: первый неотвеченный вопрос, иначе первый вопрос. */
export function firstIndexOfChapter(
  chapters: Chapter[],
  chapterIndex: number,
  answers: Record<number, number>,
): number {
  const flatStart = chapters.slice(0, chapterIndex).reduce((sum, c) => sum + c.questions.length, 0);
  const chapter = chapters[chapterIndex];
  if (!chapter) return 0;
  const firstUnanswered = chapter.questions.findIndex((q) => answers[q.id] === undefined);
  return flatStart + (firstUnanswered === -1 ? 0 : firstUnanswered);
}
