import type { AssessmentQuestion } from '../../types/assessment';

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
 *
 * Имена критерия и главы берутся ИЗ САМОГО ВОПРОСА, а не из справочника
 * критериев. Справочник отдаёт только действующую методику (без
 * is_archived), а опубликованная редакция анкеты может содержать вопросы
 * критерия, заархивированного позже — архивирование прошлые редакции не
 * переписывает (7l). Раньше такой вопрос молча выпадал из группировки:
 * бэкенд считал его обязательным («28 из 31»), а показать его на экране
 * было негде, и анкета не могла завершиться никогда.
 */
export function groupQuestionsIntoChapters(questions: AssessmentQuestion[]): Chapter[] {
  const ordered = [...questions].sort(
    (a, b) =>
      a.outcome_area_order - b.outcome_area_order ||
      a.competency_order - b.competency_order ||
      a.order - b.order,
  );

  const chapters: Chapter[] = [];
  for (const question of ordered) {
    const last = chapters[chapters.length - 1];
    const groupedQuestion: GroupedQuestion = { ...question, competencyName: question.competency_name };
    if (last && last.outcomeAreaId === question.outcome_area_id) {
      last.questions.push(groupedQuestion);
    } else {
      chapters.push({
        outcomeAreaId: question.outcome_area_id,
        name: question.outcome_area_name,
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
