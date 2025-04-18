import { Button, Form, Input, Modal, Spin, Typography } from "antd";
import { useContext, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../../api";
import { SurveyAnswersRequest, SurveyAnswersResponse } from "../../api/survey/types";
import { reactMarkdownOptions } from "../../constants";
import { UserContext } from "../../providers/UserProvider";

const { Title } = Typography;

interface SurveyModalProps {
  open: boolean;
  onClose: () => void;
}

export const SurveyModal = ({ open, onClose }: SurveyModalProps) => {
  const { user } = useContext(UserContext);
  const [loading, setLoading] = useState(false);
  const [questions, setQuestions] = useState<string[]>([]);
  const [savedAnswers, setSavedAnswers] = useState<SurveyAnswersResponse | null>(null);
  const [form] = Form.useForm();
  const [summaryModalOpen, setSummaryModalOpen] = useState(false);
  const [summaryData, setSummaryData] = useState("");

  const loadData = async () => {
    try {
      setLoading(true);
      
      const [questionsResponse, answersResponse] = await Promise.all([
        api.survey.getQuestions(),
        api.survey.getAnswers(user!)
      ]);

      setQuestions(questionsResponse);
      setSavedAnswers(answersResponse);
    } catch (error) {
      console.error('Error loading survey data:', error);
    } finally {
      setLoading(false);
    }
  };

  const mapAnswersToFormValues = (answers: string[]) => {
    return {
      question1: answers[0] || '',
      question2: answers[1] || '',
      question3: answers[2] || '',
      question4: answers[3] || '',
      question5: answers[4] || '',
    };
  };

  useEffect(() => {
    if (savedAnswers && questions.length > 0) {
      form.setFieldsValue(mapAnswersToFormValues(savedAnswers.answers));
    }
  }, [savedAnswers, questions, form]);

  const handleSubmit = async (values: Record<string, string>) => {
    if (!user) return;

    const answers: SurveyAnswersRequest = {
      user_id: user,
      question_1: values.question1,
      question_2: values.question2,
      question_3: values.question3,
      question_4: values.question4,
      question_5: values.question5,
    };

    try {
      setLoading(true);
      const response = await api.survey.submitAnswers(answers);
      setSummaryData(response.summary); // Сохраняем сводку
      onClose(); // Закрываем модалку с анкетой
      setSummaryModalOpen(true); // Открываем модалку с результатом
    } catch (error) {
      console.error('Error submitting answers:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && user) {
      loadData();
      form.resetFields();
    }
  }, [open, user, form]);

  return (
    <>
      <Modal
        title={<Title level={4}>Инвестиционная анкета</Title>}
        open={open}
        onCancel={onClose}
        footer={null}
        width={900}
        destroyOnClose
        style={{ top: 10, bottom: 10 }}
      >
        <Spin spinning={loading}>
          <Form
            form={form}
            layout="vertical"
            onFinish={handleSubmit}
            autoComplete="off"
          >
            {questions.map((question, index) => (
              <Form.Item
                key={index}
                name={`question${index + 1}`}
                label={`Вопрос ${index + 1}: ${question}`}
                rules={[{ required: true, message: 'Пожалуйста, ответьте на вопрос' }]}
              >
                <Input.TextArea 
                  rows={3} 
                  allowClear
                  showCount 
                  maxLength={500}
                  disabled={loading}
                />
              </Form.Item>
            ))}

            <Form.Item>
              <Button 
                type="primary" 
                htmlType="submit" 
                loading={loading}
                disabled={loading}
                block
                size="large"
              >
                {savedAnswers ? 'Обновить ответы' : 'Отправить ответы'}
              </Button>
            </Form.Item>
          </Form>
        </Spin>
      </Modal>

      {/* Модалка для отображения сводки */}
      <Modal
        title="Результаты анкетирования"
        open={summaryModalOpen}
        onCancel={() => setSummaryModalOpen(false)}
        footer={[
          <Button 
            key="close" 
            type="primary" 
            onClick={() => setSummaryModalOpen(false)}
          >
            Закрыть
          </Button>
        ]}
        width={800}
      >
        {summaryData ? (
          <div style={{ 
            padding: 16, 
            background: '#f9f9f9', 
            borderRadius: 8,
            maxHeight: '60vh',
            overflowY: 'auto'
          }}>
            <ReactMarkdown {...reactMarkdownOptions}>
              {summaryData}
            </ReactMarkdown>
          </div>
        ) : (
          <Spin tip="Формирование сводки..." />
        )}
      </Modal>
    </>
  );
};