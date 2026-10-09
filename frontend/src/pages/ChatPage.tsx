import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, ArrowUpRight, LoaderCircle } from "lucide-react";
import { api, type Conversation, type Reply } from "../api";
import Citation from "../components/Citation";

interface Props {
  question: string;
  setQuestion: (question: string) => void;
}
export default function ChatPage({ question, setQuestion }: Props) {
  const client = useQueryClient();
  const bottom = useRef<HTMLDivElement>(null);
  const history = useQuery({
    queryKey: ["history"],
    queryFn: () => api<Conversation[]>("/chat"),
  });
  const chat = useMutation({
    mutationFn: (query: string) =>
      api<Reply>("/chat", { method: "POST", body: JSON.stringify({ query }) }),
    onMutate: () => {
      setQuestion("");
      return new Set(history.data?.map((item) => item.id));
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["history"] }),
  });
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history.data?.length, chat.isPending]);
  const submit = () => {
    const text = question.trim();
    if (text && !chat.isPending) chat.mutate(text);
  };
  const sent =
    (chat.isPending || chat.isError) &&
    !history.data?.some(
      (item) => item.question === chat.variables && !chat.context?.has(item.id),
    );
  const populated = !!history.data?.length || sent;
  return (
    <section className={`conversation-page ${populated ? "populated" : ""}`}>
      {!populated && (
        <div className="conversation-intro">
          <span className="kicker">Your knowledge, in conversation</span>
          <h1>
            Follow a thought
            <br />
            <em>a little further.</em>
          </h1>
          <p>Answers with a path back to the source.</p>
        </div>
      )}
      <div className="messages">
        {history.data?.map((item) => (
          <article className="exchange" key={item.id}>
            <div className="question">{item.question}</div>
            <div className="answer">
              <span className="answer-mark">✳</span>
              <div>
                <p>{item.answer}</p>
                <div className="citations">
                  {item.citations.map((e, i) => (
                    <Citation key={i} evidence={e} number={i + 1} />
                  ))}
                </div>
              </div>
            </div>
          </article>
        ))}
        {sent && <div className="question">{chat.variables}</div>}
        {sent && chat.isPending && (
          <div className="thinking" role="status" aria-live="polite">
            <LoaderCircle className="spin" size={15} />
            Reading your sources…
          </div>
        )}
        {chat.error && (
          <p className="error" role="alert">
            {chat.error.message}
            <button
              className="text-action"
              onClick={() => chat.variables && chat.mutate(chat.variables)}
            >
              Retry question
            </button>
          </p>
        )}
        <div ref={bottom} />
      </div>
      <div className="conversation-composer">
        <form
          className="chat-input glass"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <textarea
            rows={2}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="What are you curious about?"
            maxLength={2000}
            aria-label="Question for Lumi"
          />
          <div>
            <span>From your sources</span>
            <button
              className="send-button"
              disabled={!question.trim() || chat.isPending}
              aria-label="Send question"
            >
              <ArrowUp size={19} />
            </button>
          </div>
        </form>
        {!populated && (
          <div className="question-suggestions">
            {[
              "Find the key ideas in my sources",
              "How are these ideas connected?",
            ].map((q) => (
              <button key={q} onClick={() => setQuestion(q)}>
                {q}
                <ArrowUpRight size={12} />
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
